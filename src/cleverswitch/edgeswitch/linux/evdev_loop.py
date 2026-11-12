from __future__ import annotations

import dataclasses
import errno
import logging
import time
from collections.abc import Callable

from ...hotplug.linux.udev_message import ACTION_REMOVE, input_node_event, sender_uid
from ...model.config.edge import Edge
from ..loop_backend import LoopFactory
from ..push_detector import PushDetector
from .evdev_io import EvdevIO
from .input_caps import is_keyboard, is_pointer
from .input_event import (
    BUTTONS,
    EV_KEY,
    EV_REL,
    EV_SYN,
    EVENT_SIZE,
    MODIFIER_KEYS,
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

PERMISSION_HINT = (
    "Edge switch cannot read any keyboard or mouse in /dev/input; add your user to the 'input' group "
    "or install the opt-in rules.d/43-cleverswitch-input.rules"
)
GRAB_CHECK_INTERVAL_S = 1.0


@dataclasses.dataclass
class _Device:
    node: str
    fd: int
    keyboard: bool
    pressed: set[int] = dataclasses.field(default_factory=set)
    dx: int = 0
    dy: int = 0
    grab_warned: bool = False


class EvdevInputLoop:
    """Reads keyboards and mice from /dev/input for sessions where the cursor position cannot be read
    (Wayland) and feeds held modifiers and relative motion to a PushDetector.

    Devices come and go through udevd's netlink messages, which arrive after the rules ran, so a node's
    ACL is already in place; a change message (udevadm trigger after a rule is installed) retries a node
    that was refused. The socket is bound before the first scan, so no device can slip between the two.
    """

    def __init__(
        self,
        io: EvdevIO,
        detector: PushDetector,
        publish: Callable[[Edge], None],
        clock: Callable[[], float] = time.monotonic,
    ):
        self._io = io
        self._detector = detector
        self._publish = publish
        self._clock = clock
        self._devices: dict[int, _Device] = {}
        self._wake_r: int | None = None
        self._wake_w: int | None = None
        self._udev_fd: int | None = None
        self._interrupted = False
        self._denied = False
        self._permission_warned = False
        self._next_grab_check = float("-inf")
        try:
            self._wake_r, self._wake_w = io.pipe()
            self._udev_fd = io.open_udev()
            self._scan()
        except BaseException:
            self.close()
            raise
        log.info(f"Edge switch reads {len(self._devices)} input devices")

    @classmethod
    def factory(cls, detector: PushDetector, io_factory: Callable[[], EvdevIO] = EvdevIO) -> LoopFactory:
        def build(publish, _stopping) -> EvdevInputLoop:
            return cls(io_factory(), detector, publish)

        return build

    def run(self) -> None:
        while not self._interrupted:
            for fd in self._io.poll([self._wake_r, self._udev_fd, *self._devices], -1):
                if self._interrupted:
                    return
                if fd == self._udev_fd:
                    self._on_udev()
                elif (device := self._devices.get(fd)) is not None:
                    self._read(device)

    def interrupt(self) -> None:
        self._interrupted = True
        self._io.wake(self._wake_w)

    def close(self) -> None:
        for fd in list(self._devices):
            self._io.close(fd)
        self._devices.clear()
        self._io.close_udev()
        for fd in (self._wake_r, self._wake_w):
            if fd is not None:
                self._io.close(fd)
        self._wake_r = self._wake_w = None

    def _on_udev(self) -> None:
        try:
            message = self._io.receive_udev()
        except OSError as e:
            if e.errno != errno.ENOBUFS:
                raise
            log.debug("udev input events were lost; rescanning /dev/input")
            self._scan()
            return
        if message is None:
            return
        data, ancdata = message
        if sender_uid(ancdata) != 0:
            return
        parsed = input_node_event(data)
        if parsed is None:
            return
        action, node = parsed
        known = next((d for d in self._devices.values() if d.node == node), None)
        if action == ACTION_REMOVE:
            if known is not None:
                self._drop(known)
        elif known is None:
            self._try_open(node)
            self._warn_if_nothing_readable()

    def _scan(self) -> None:
        known = {d.node for d in self._devices.values()}
        for node in self._io.list_nodes():
            if node not in known:
                self._try_open(node)
        self._warn_if_nothing_readable()

    def _try_open(self, node: str) -> None:
        key_caps, rel_caps = self._io.read_caps(node)
        keyboard = is_keyboard(key_caps)
        if not keyboard and not is_pointer(key_caps, rel_caps):
            return
        try:
            fd = self._io.open(node)
        except PermissionError:
            self._denied = True
            return
        except OSError as e:
            log.debug(f"Cannot open {node}: {e}")
            return
        device = _Device(node=node, fd=fd, keyboard=keyboard)
        self._refresh_keys(device)
        self._devices[fd] = device
        self._update_state()
        log.debug(f"Edge switch reads {node}")

    def _warn_if_nothing_readable(self) -> None:
        if self._denied and not self._devices and not self._permission_warned:
            log.warning(PERMISSION_HINT)
            self._permission_warned = True
        self._denied = False

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
        if not self._detector.active:
            self._check_grabs()
            return
        edge = self._detector.on_motion(dx, dy)
        if edge is not None:
            self._publish(edge)

    # Another program's EVIOCGRAB (OpenLogi, input-remapper, keyd...) silently starves this reader, but the
    # kernel's key state still shows what is held. A modifier held there that no device reported means the
    # keyboard is grabbed; a release we missed is resynced. Checked at most once a second, only while
    # moving without the gesture, so it costs nothing in normal use.
    def _check_grabs(self) -> None:
        now = self._clock()
        if now < self._next_grab_check:
            return
        self._next_grab_check = now + GRAB_CHECK_INTERVAL_S
        for device in [d for d in self._devices.values() if d.keyboard]:
            self._read(device)  # events already queued are not missed ones
            if device.fd not in self._devices:
                continue
            try:
                kernel = pressed_keys(self._io.key_state(device.fd))
            except OSError:
                continue
            if device.pressed - kernel:
                device.pressed &= kernel
                self._update_state()
            reported = set().union(*(d.pressed for d in self._devices.values()))
            unseen = {code for code in kernel - reported if code in MODIFIER_KEYS}
            if unseen and not device.grab_warned:
                device.grab_warned = True
                log.warning(
                    f"Edge switch cannot see '{self._io.device_name(device.node)}' ({device.node}): another "
                    f"program (OpenLogi, input-remapper, keyd...) holds it exclusively and re-sends its input "
                    f"elsewhere"
                )

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
