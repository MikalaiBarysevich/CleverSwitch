from __future__ import annotations

import logging
from collections.abc import Callable

from ...model.config.modifier import Modifier
from ..edge_detector import EdgeDetector
from ..edge_sink import EdgeSink, Location
from ..geometry import Rect, union
from ..loop_backend import LoopFactory
from .quartz import (
    LEFT_MOUSE_DRAGGED,
    MOUSE_MOVED,
    OTHER_MOUSE_DRAGGED,
    RIGHT_MOUSE_DRAGGED,
    TAP_DISABLED_BY_TIMEOUT,
    TAP_DISABLED_BY_USER_INPUT,
    Quartz,
)

log = logging.getLogger(__name__)

PERMISSION_HINT = "grant CleverSwitch Input Monitoring in System Settings > Privacy & Security"

# CGEventFlags device-independent masks; each covers the left and right key.
MODIFIER_FLAGS = {
    0x00040000: Modifier.CTRL,  # kCGEventFlagMaskControl
    0x00020000: Modifier.SHIFT,  # kCGEventFlagMaskShift
    0x00080000: Modifier.ALT,  # kCGEventFlagMaskAlternate
    0x00100000: Modifier.META,  # kCGEventFlagMaskCommand
}
MOUSE_BUTTONS = range(5)  # left, right, center, and two extra buttons
MOTION_EVENTS = frozenset({MOUSE_MOVED, LEFT_MOUSE_DRAGGED, RIGHT_MOUSE_DRAGGED, OTHER_MOUSE_DRAGGED})


class EventTapLoop:
    """macOS input through a listen-only event tap: every mouse event carries its location and the modifier
    flags. macOS disables a tap whose callback is too slow; it is re-enabled at once, and if that fails
    (Input Monitoring revoked) the loop ends so the backend reports the source lost."""

    def __init__(self, quartz: Quartz, sink: EdgeSink):
        self._quartz = quartz
        self._sink = sink
        self._interrupted = False
        self._error: Exception | None = None
        self._warned = False
        if not quartz.listen_access_granted():
            raise PermissionError(PERMISSION_HINT)
        try:
            quartz.open_tap(self._on_event)
        except PermissionError as e:
            raise PermissionError(PERMISSION_HINT) from e

    @classmethod
    def factory(cls, quartz_factory: Callable[[], Quartz], detector: EdgeDetector) -> LoopFactory:
        def build(publish, stopping) -> EventTapLoop:
            return cls(quartz_factory(), EdgeSink(detector, publish, stopping))

        return build

    def run(self) -> None:
        while not self._interrupted:
            self._quartz.run()
            if self._error is not None:
                raise self._error

    def interrupt(self) -> None:
        self._interrupted = True
        self._quartz.wake_stop()

    def close(self) -> None:
        self._quartz.close_tap()

    def _on_event(self, event_type: int, event: int) -> None:
        try:
            if event_type in (TAP_DISABLED_BY_TIMEOUT, TAP_DISABLED_BY_USER_INPUT):
                self._reenable()
                return
            flags = self._quartz.event_flags(event)
            modifiers = Modifier.NONE
            for mask, modifier in MODIFIER_FLAGS.items():
                if flags & mask:
                    modifiers |= modifier
            buttons_held = any(self._quartz.button_down(b) for b in MOUSE_BUTTONS)
            self._sink.on_state(modifiers, buttons_held)
            if event_type in MOTION_EVENTS:
                self._sink.on_motion(lambda: self._locate(event))
        except Exception as e:
            if not self._warned:
                log.warning(f"Edge switch cannot handle an input event: {e!r}")
                self._warned = True

    def _reenable(self) -> None:
        if self._quartz.reenable_tap():
            log.debug("Re-enabled the edge-switch event tap")
            return
        self._error = PermissionError(f"the event tap was disabled; {PERMISSION_HINT}")
        self._quartz.stop_run()

    def _locate(self, event: int) -> Location:
        x, y = self._quartz.event_location(event)
        bounds = union(
            Rect(dx, dy, dx + w, dy + h) for dx, dy, w, h in self._quartz.display_bounds() if w > 0 and h > 0
        )
        return x, y, bounds
