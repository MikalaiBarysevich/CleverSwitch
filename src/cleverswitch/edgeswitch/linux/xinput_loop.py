from __future__ import annotations

import os
import select
from collections.abc import Callable

from ...model.config.modifier import Modifier
from ..edge_detector import EdgeDetector
from ..edge_sink import EdgeSink, Location
from ..geometry import Rect
from ..loop_backend import LoopFactory
from . import x11_events
from .x11_events import ConfigureEvent, MappingEvent, RawEvent
from .x11_keymap import BUTTON_MASK, modifier_keycodes, modifiers_from_keymap
from .xcb import Xcb

_KEY_EVENTS = frozenset({x11_events.XI_RAW_KEY_PRESS, x11_events.XI_RAW_KEY_RELEASE})
_BUTTON_EVENTS = frozenset({x11_events.XI_RAW_BUTTON_PRESS, x11_events.XI_RAW_BUTTON_RELEASE})
_HELD_BUTTONS = frozenset({1, 2, 3})  # 4..7 are the scroll wheel, down only for an instant


class XInputLoop:
    """X11 input through XInput 2 raw events, which reach the root window whatever client has focus or a
    grab. An event only says what changed; the modifiers, buttons and cursor are read from the server once
    per burst, after the events queued so far are drained."""

    def __init__(self, xcb: Xcb, sink: EdgeSink):
        self._xcb = xcb
        self._sink = sink
        self._opcode = xcb.enable_raw_events()
        self._keycodes = self._load_keycodes()
        self._bounds = _rect(xcb.root_geometry())
        self._interrupted = False
        self._refresh_state()
        self._wake_r, self._wake_w = os.pipe()

    @classmethod
    def factory(cls, xcb_factory: Callable[[], Xcb], detector: EdgeDetector) -> LoopFactory:
        def build(publish, stopping) -> XInputLoop:
            xcb = xcb_factory()
            try:
                return cls(xcb, EdgeSink(detector, publish, stopping))
            except BaseException:
                xcb.close()
                raise

        return build

    def run(self) -> None:
        poller = select.poll()
        poller.register(self._xcb.fd(), select.POLLIN)
        poller.register(self._wake_r, select.POLLIN)
        while not self._interrupted:
            self._drain()
            self._xcb.flush()
            poller.poll()

    def interrupt(self) -> None:
        self._interrupted = True
        os.write(self._wake_w, b"\0")

    def close(self) -> None:
        os.close(self._wake_r)
        os.close(self._wake_w)
        self._xcb.close()

    def _drain(self) -> None:
        state_changed = moved = False
        while (raw := self._xcb.next_event()) is not None:
            event = x11_events.decode(raw, self._opcode)
            if isinstance(event, RawEvent):
                if event.event_type in _KEY_EVENTS:
                    state_changed |= event.detail in self._keycodes
                elif event.event_type in _BUTTON_EVENTS:
                    state_changed |= event.detail in _HELD_BUTTONS
                elif event.event_type == x11_events.XI_RAW_MOTION:
                    moved = True
            elif isinstance(event, ConfigureEvent):
                if event.window == self._xcb.root:
                    self._bounds = _rect((0, 0, event.width, event.height))
            elif isinstance(event, MappingEvent):
                if event.request in (x11_events.MAPPING_MODIFIER, x11_events.MAPPING_KEYBOARD):
                    self._keycodes = self._load_keycodes()
                    state_changed = True
        if self._xcb.has_error():
            raise OSError("lost the X server connection")
        if state_changed:
            self._refresh_state()
        if moved:
            self._sink.on_motion(self._locate)

    def _load_keycodes(self) -> dict[int, Modifier]:
        mapping = self._xcb.keyboard_mapping()
        return modifier_keycodes(*mapping) if mapping is not None else {}

    def _refresh_state(self) -> None:
        keymap = self._xcb.query_keymap()
        pointer = self._xcb.query_pointer()
        if keymap is None or pointer is None:
            return
        self._sink.on_state(modifiers_from_keymap(keymap, self._keycodes), bool(pointer[2] & BUTTON_MASK))

    def _locate(self) -> Location | None:
        pointer = self._xcb.query_pointer()
        if pointer is None:
            return None
        return pointer[0], pointer[1], self._bounds


def _rect(geometry: tuple[int, int, int, int] | None) -> Rect | None:
    if geometry is None:
        return None
    x, y, width, height = geometry
    return Rect(x, y, x + width, y + height) if width > 0 and height > 0 else None
