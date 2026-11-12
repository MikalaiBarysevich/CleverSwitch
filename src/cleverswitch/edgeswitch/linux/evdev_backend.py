from __future__ import annotations

import dataclasses
import errno
import logging
import threading
import time
from collections.abc import Callable

from ...errors.errors import EdgeSwitchError
from ...event.edge_touched_event import EdgeTouchedEvent
from ...topic.topics import Topics
from ..backend import EdgeBackend
from ..push_detector import PushDetector
from .evdev_io import EvdevIO
from .input_caps import is_keyboard, is_pointer
from .input_event import (
    BUTTONS,
    EV_KEY,
    EV_REL,
    EV_SYN,
    EVENT_SIZE,
    REL_X,
    REL_Y,
    SYN_DROPPED,
    SYN_REPORT,
    TRACKED_KEYS,
    held_modifiers,
    parse_events,
    pressed_keys,
)

log = logging.getLogger(__name__)

RESCAN_INTERVAL_S = 2.0
_POLL_TIMEOUT_MS = 500
_STOP_JOIN_TIMEOUT = 2.0
PERMISSION_HINT = (
    "no permission to read /dev/input; add your user to the 'input' group "
    "or install the opt-in rules.d/43-cleverswitch-input.rules"
)


@dataclasses.dataclass
class _Device:
    node: str
    fd: int
    pressed: set[int] = dataclasses.field(default_factory=set)
    dx: int = 0
    dy: int = 0


class EvdevEdgeBackend(EdgeBackend):
    """Reads keyboards and mice from /dev/input for sessions where the cursor position cannot be read
    (Wayland). Feeds held modifiers and relative motion to a PushDetector."""

    def __init__(
        self,
        detector: PushDetector,
        topics: Topics,
        io_factory: Callable[[], EvdevIO] = EvdevIO,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._detector = detector
        self._topics = topics
        self._io = io_factory()
        self._clock = clock
        self._devices: dict[int, _Device] = {}
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()
        self._wake_r: int | None = None
        self._wake_w: int | None = None

    def start(self) -> None:
        opened, denied = self._scan()
        if not opened and denied:
            raise EdgeSwitchError(PERMISSION_HINT)
        if not opened:
            log.info("No keyboard or mouse in /dev/input yet; will keep looking")
        self._wake_r, self._wake_w = self._io.pipe()
        self._thread = threading.Thread(target=self._run, name="edge-evdev", daemon=True)
        self._thread.start()
        log.info(f"Watching screen edges (edge-evdev, {opened} input devices)")

    def stop(self) -> None:
        thread, self._thread = self._thread, None
        if thread is None:
            return
        self._stopping.set()
        self._io.wake(self._wake_w)
        thread.join(timeout=_STOP_JOIN_TIMEOUT)

    def revive(self) -> None:
        pass

    def _run(self) -> None:
        next_scan = self._clock() + RESCAN_INTERVAL_S
        try:
            while not self._stopping.is_set():
                if self._clock() >= next_scan:
                    self._scan()
                    next_scan = self._clock() + RESCAN_INTERVAL_S
                ready = self._io.poll([*self._devices, self._wake_r], _POLL_TIMEOUT_MS)
                for fd in ready:
                    if fd in self._devices:
                        self._read(self._devices[fd])
        finally:
            for fd in list(self._devices):
                self._io.close(fd)
            self._devices.clear()
            self._io.close(self._wake_r)
            self._io.close(self._wake_w)

    # Returns (devices opened, devices refused for lack of permission).
    def _scan(self) -> tuple[int, int]:
        known = {d.node for d in self._devices.values()}
        opened = denied = 0
        for node in self._io.list_nodes():
            if node in known:
                continue
            key_caps, rel_caps = self._io.read_caps(node)
            if not is_keyboard(key_caps) and not is_pointer(key_caps, rel_caps):
                continue
            try:
                fd = self._io.open(node)
            except PermissionError:
                denied += 1
                continue
            except OSError as e:
                log.debug(f"Cannot open {node}: {e}")
                continue
            self._warn_if_grabbed(node, fd)
            device = _Device(node=node, fd=fd)
            self._refresh_keys(device)
            self._devices[fd] = device
            opened += 1
            log.debug(f"Edge switch reads {node}")
        if opened:
            self._update_state()
        return opened, denied

    # The device stays open: the grab may end later (the other program quits).
    def _warn_if_grabbed(self, node: str, fd: int) -> None:
        try:
            grabbed = self._io.is_grabbed(fd)
        except OSError:
            return
        if grabbed:
            log.warning(
                f"Edge switch cannot see '{self._io.device_name(node)}' ({node}): another program "
                f"(OpenLogi, input-remapper, keyd...) holds it exclusively and re-sends its input elsewhere"
            )

    def _read(self, device: _Device) -> None:
        try:
            data = self._io.read(device.fd, EVENT_SIZE)
        except OSError as e:
            if e.errno != errno.ENODEV:
                log.debug(f"Read from {device.node} failed: {e}")
            self._drop(device)
            return
        for etype, code, value in parse_events(data):
            if etype == EV_KEY and code in TRACKED_KEYS:
                if value:
                    device.pressed.add(code)
                else:
                    device.pressed.discard(code)
                self._update_state()
            elif etype == EV_REL and code == REL_X:
                device.dx += value
            elif etype == EV_REL and code == REL_Y:
                device.dy += value
            elif etype == EV_SYN and code == SYN_REPORT:
                self._report_motion(device)
            elif etype == EV_SYN and code == SYN_DROPPED:
                device.dx = device.dy = 0
                self._refresh_keys(device)
                self._update_state()

    def _report_motion(self, device: _Device) -> None:
        dx, dy = device.dx, device.dy
        device.dx = device.dy = 0
        if not dx and not dy:
            return
        edge = self._detector.on_motion(dx, dy)
        if edge is not None:
            self._topics.edge.publish(EdgeTouchedEvent(slot=0, pid=0, edge=edge))

    def _refresh_keys(self, device: _Device) -> None:
        try:
            device.pressed = pressed_keys(self._io.key_state(device.fd))
        except OSError:
            device.pressed = set()

    def _drop(self, device: _Device) -> None:
        self._devices.pop(device.fd, None)
        self._io.close(device.fd)
        log.debug(f"Edge switch stopped reading {device.node}")
        self._update_state()

    def _update_state(self) -> None:
        pressed = set().union(*(d.pressed for d in self._devices.values()))
        self._detector.on_state(held_modifiers(pressed), bool(pressed & BUTTONS))
