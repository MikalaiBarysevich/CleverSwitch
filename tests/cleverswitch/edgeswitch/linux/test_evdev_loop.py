import errno
import logging
import socket
import struct
import threading
from unittest.mock import MagicMock

import pytest

from cleverswitch.edgeswitch.linux.evdev_loop import GRAB_CHECK_INTERVAL_S, PERMISSION_HINT, EvdevInputLoop
from cleverswitch.edgeswitch.linux.input_event import EV_KEY, EV_REL, EV_SYN, REL_X, REL_Y, SYN_DROPPED, SYN_REPORT
from cleverswitch.model.config.edge import Edge
from cleverswitch.model.config.modifier import Modifier

KBD_CAPS = ("20000000", "0")  # bit 29 = KEY_LEFTCTRL
MOUSE_CAPS = ("1f0000 0 0 0 0", "3")  # BTN_LEFT.., REL_X|REL_Y
OTHER_CAPS = ("0", "0")
WAKE_R, WAKE_W, UDEV = 98, 99, 97
ROOT = 0


def _ev(etype, code, value):
    return struct.pack("llHHi", 0, 0, etype, code, value)


def _key_state(*codes):
    state = bytearray(96)
    for code in codes:
        state[code // 8] |= 1 << (code % 8)
    return bytes(state)


def _udev(action, node, uid=ROOT, subsystem="input"):
    body = b"".join(
        f"{k}={v}".encode() + b"\0" for k, v in {"ACTION": action, "SUBSYSTEM": subsystem, "DEVNAME": node}.items()
    )
    data = b"libudev\0" + struct.pack(">I", 0xFEEDCAFE) + struct.pack("=IIIIIII", 40, 40, len(body), 0, 0, 0, 0) + body
    return data, [(socket.SOL_SOCKET, socket.SCM_CREDENTIALS, struct.pack("=iII", 1, uid, uid))]


class FakeIO:
    def __init__(self, nodes=()):
        self.nodes = dict(nodes)  # node -> caps
        self.denied = set()
        self.broken = set()
        self.fds = {}
        self.data = {}
        self.read_errors = {}
        self.states = {}
        self.closed = []
        self.udev = []
        self.udev_open_error = None
        self.udev_closed = False
        self.woken = False
        self.on_idle = None
        self._next_fd = 10

    def pipe(self):
        return WAKE_R, WAKE_W

    def wake(self, _fd):
        self.woken = True

    def open_udev(self):
        if self.udev_open_error:
            raise self.udev_open_error
        return UDEV

    def receive_udev(self):
        if not self.udev:
            return None
        message = self.udev.pop(0)
        if isinstance(message, Exception):
            raise message
        return message

    def close_udev(self):
        self.udev_closed = True

    def list_nodes(self):
        return list(self.nodes)

    def read_caps(self, node):
        return self.nodes[node]

    def device_name(self, node):
        return f"name of {node}"

    def open(self, node):
        if node in self.denied:
            raise PermissionError(errno.EACCES, "denied")
        if node in self.broken:
            raise OSError(errno.EBUSY, "busy")
        fd = self._next_fd
        self._next_fd += 1
        self.fds[node] = fd
        return fd

    def key_state(self, fd):
        state = self.states.get(fd)
        if isinstance(state, Exception):
            raise state
        return state or _key_state()

    def read(self, fd, _event_size):
        if fd in self.read_errors:
            raise self.read_errors.pop(fd)
        chunks = self.data.get(fd, [])
        return chunks.pop(0) if chunks else b""

    def close(self, fd):
        self.closed.append(fd)

    def poll(self, fds, timeout_ms):
        assert timeout_ms == -1
        ready = [fd for fd in fds if self.data.get(fd) or fd in self.read_errors]
        if self.udev and UDEV in fds:
            ready.append(UDEV)
        if self.woken:
            ready.append(WAKE_R)
        if not ready and self.on_idle is not None:
            self.on_idle()
        return ready


def _loop(io, detector=None, publish=None, clock=lambda: 0.0):
    if detector is None:
        detector = MagicMock()
        detector.active = True
    return EvdevInputLoop(io, detector, publish or MagicMock(), clock=clock)


def test_opens_keyboards_and_mice_only():
    io = FakeIO({"/dev/input/event1": KBD_CAPS, "/dev/input/event2": MOUSE_CAPS, "/dev/input/event3": OTHER_CAPS})
    loop = _loop(io)
    assert {d.node for d in loop._devices.values()} == {"/dev/input/event1", "/dev/input/event2"}
    assert [d.keyboard for d in loop._devices.values()] == [True, False]


def test_nothing_readable_warns_once_and_keeps_running(caplog):
    io = FakeIO({"/dev/input/event1": KBD_CAPS})
    io.denied.add("/dev/input/event1")
    loop = _loop(io)
    io.udev.append(_udev("change", "/dev/input/event1"))
    loop._on_udev()
    assert caplog.text.count(PERMISSION_HINT) == 1


def test_one_refused_device_beside_a_readable_one_is_no_warning(caplog):
    io = FakeIO({"/dev/input/event1": KBD_CAPS, "/dev/input/event2": MOUSE_CAPS})
    io.denied.add("/dev/input/event1")
    _loop(io)
    assert PERMISSION_HINT not in caplog.text


def test_empty_system_is_no_warning(caplog):
    _loop(FakeIO())
    assert PERMISSION_HINT not in caplog.text


def test_busy_device_is_skipped():
    io = FakeIO({"/dev/input/event1": KBD_CAPS})
    io.broken.add("/dev/input/event1")
    assert _loop(io)._devices == {}


def test_failed_setup_closes_what_was_opened():
    io = FakeIO()
    io.udev_open_error = OSError("no netlink")
    with pytest.raises(OSError, match="no netlink"):
        _loop(io)
    assert {WAKE_R, WAKE_W} <= set(io.closed)
    assert io.udev_closed


def test_initial_key_state_is_reported():
    io = FakeIO({"/dev/input/event1": KBD_CAPS})
    io.states[10] = _key_state(29)
    detector = MagicMock()
    _loop(io, detector)
    detector.on_state.assert_called_with(Modifier.CTRL, False)


def test_unreadable_key_state_counts_as_nothing_pressed():
    io = FakeIO({"/dev/input/event1": KBD_CAPS})
    io.states[10] = OSError("nope")
    detector = MagicMock()
    _loop(io, detector)
    detector.on_state.assert_called_with(Modifier.NONE, False)


def test_key_and_motion_events_drive_the_detector():
    io = FakeIO({"/dev/input/event1": KBD_CAPS, "/dev/input/event2": MOUSE_CAPS})
    detector = MagicMock()
    detector.active = True
    detector.on_motion.return_value = Edge.RIGHT
    publish = MagicMock()
    loop = _loop(io, detector, publish)
    kbd, mouse = loop._devices[10], loop._devices[11]

    io.data[10] = [_ev(EV_KEY, 97, 1) + _ev(EV_SYN, SYN_REPORT, 0)]
    loop._read(kbd)
    detector.on_state.assert_called_with(Modifier.CTRL, False)

    io.data[11] = [
        _ev(EV_KEY, 0x110, 1)
        + _ev(EV_REL, REL_X, 7)
        + _ev(EV_REL, REL_Y, -2)
        + _ev(EV_REL, REL_X, 3)
        + _ev(EV_SYN, SYN_REPORT, 0)
        + _ev(EV_SYN, SYN_REPORT, 0)
    ]
    loop._read(mouse)
    detector.on_state.assert_called_with(Modifier.CTRL, True)
    detector.on_motion.assert_called_once_with(10, -2)
    publish.assert_called_once_with(Edge.RIGHT)

    io.data[10] = [_ev(EV_KEY, 97, 0)]
    loop._read(kbd)
    detector.on_state.assert_called_with(Modifier.NONE, True)


def test_untracked_keys_are_ignored():
    io = FakeIO({"/dev/input/event1": KBD_CAPS})
    detector = MagicMock()
    loop = _loop(io, detector)
    detector.reset_mock()
    io.data[10] = [_ev(EV_KEY, 30, 1)]
    loop._read(loop._devices[10])
    detector.on_state.assert_not_called()


def test_motion_without_an_edge_publishes_nothing():
    io = FakeIO({"/dev/input/event2": MOUSE_CAPS})
    detector = MagicMock()
    detector.active = True
    detector.on_motion.return_value = None
    publish = MagicMock()
    loop = _loop(io, detector, publish)
    io.data[10] = [_ev(EV_REL, REL_X, 5) + _ev(EV_SYN, SYN_REPORT, 0)]
    loop._read(loop._devices[10])
    publish.assert_not_called()


def test_dropped_events_resync_key_state():
    io = FakeIO({"/dev/input/event1": KBD_CAPS})
    detector = MagicMock()
    loop = _loop(io, detector)
    device = loop._devices[10]
    device.dx = 50
    io.states[10] = _key_state(29)
    io.data[10] = [_ev(EV_SYN, SYN_DROPPED, 0)]
    loop._read(device)
    assert device.dx == 0
    detector.on_state.assert_called_with(Modifier.CTRL, False)


@pytest.mark.parametrize("error", [OSError(errno.ENODEV, "gone"), OSError(errno.EIO, "io")])
def test_read_failure_drops_device_and_its_keys(error):
    io = FakeIO({"/dev/input/event1": KBD_CAPS})
    io.states[10] = _key_state(29)
    detector = MagicMock()
    loop = _loop(io, detector)
    io.read_errors[10] = error
    loop._read(loop._devices[10])
    assert loop._devices == {}
    assert 10 in io.closed
    detector.on_state.assert_called_with(Modifier.NONE, False)


def test_udev_add_opens_the_new_node():
    io = FakeIO()
    loop = _loop(io)
    io.nodes["/dev/input/event4"] = MOUSE_CAPS
    io.udev.append(_udev("add", "/dev/input/event4"))
    loop._on_udev()
    assert [d.node for d in loop._devices.values()] == ["/dev/input/event4"]


def test_udev_change_retries_a_refused_node():
    io = FakeIO({"/dev/input/event1": KBD_CAPS})
    io.denied.add("/dev/input/event1")
    loop = _loop(io)
    io.denied.clear()
    io.udev.append(_udev("change", "/dev/input/event1"))
    loop._on_udev()
    assert [d.node for d in loop._devices.values()] == ["/dev/input/event1"]


def test_udev_change_of_an_open_node_keeps_it():
    io = FakeIO({"/dev/input/event1": KBD_CAPS})
    loop = _loop(io)
    io.udev.append(_udev("change", "/dev/input/event1"))
    loop._on_udev()
    assert list(loop._devices) == [10]
    assert io.closed == []


def test_udev_remove_drops_the_node_and_its_keys():
    io = FakeIO({"/dev/input/event1": KBD_CAPS})
    io.states[10] = _key_state(29)
    detector = MagicMock()
    loop = _loop(io, detector)
    io.udev.append(_udev("remove", "/dev/input/event1"))
    loop._on_udev()
    assert loop._devices == {}
    assert 10 in io.closed
    detector.on_state.assert_called_with(Modifier.NONE, False)


def test_udev_remove_of_an_unknown_node_is_ignored():
    io = FakeIO()
    loop = _loop(io)
    io.udev.append(_udev("remove", "/dev/input/event9"))
    loop._on_udev()
    assert io.closed == []


@pytest.mark.parametrize(
    "message",
    [
        _udev("add", "/dev/input/event4", uid=1000),
        _udev("add", "/dev/hidraw4", subsystem="hidraw"),
    ],
)
def test_udev_messages_not_from_root_or_not_input_are_ignored(message):
    io = FakeIO()
    loop = _loop(io)
    io.nodes["/dev/input/event4"] = MOUSE_CAPS
    io.udev.append(message)
    loop._on_udev()
    assert loop._devices == {}


def test_nothing_pending_on_the_udev_socket_is_fine():
    loop = _loop(FakeIO())
    loop._on_udev()


def test_lost_udev_messages_rescan():
    io = FakeIO()
    loop = _loop(io)
    io.nodes["/dev/input/event4"] = MOUSE_CAPS
    io.udev.append(OSError(errno.ENOBUFS, "lost"))
    loop._on_udev()
    assert [d.node for d in loop._devices.values()] == ["/dev/input/event4"]


def test_broken_udev_socket_ends_the_loop():
    io = FakeIO()
    loop = _loop(io)
    io.udev.append(OSError(errno.EBADF, "bad"))
    with pytest.raises(OSError, match="bad"):
        loop.run()


def test_run_reads_devices_and_udev_until_interrupted():
    io = FakeIO({"/dev/input/event1": KBD_CAPS})
    detector = MagicMock()
    loop = _loop(io, detector)
    io.nodes["/dev/input/event2"] = MOUSE_CAPS
    io.udev.append(_udev("add", "/dev/input/event2"))
    io.data[10] = [_ev(EV_KEY, 42, 1)]
    io.on_idle = loop.interrupt
    loop.run()
    detector.on_state.assert_called_with(Modifier.SHIFT, False)
    assert "/dev/input/event2" in io.fds


def test_interrupt_before_run_returns_at_once():
    io = FakeIO({"/dev/input/event1": KBD_CAPS})
    loop = _loop(io)
    loop.interrupt()
    io.data[10] = [_ev(EV_KEY, 42, 1)]
    loop.run()
    assert io.data[10]  # nothing was read


def test_interrupt_from_another_thread_wakes_run():
    io = FakeIO()
    loop = _loop(io)
    io.on_idle = lambda: threading.Thread(target=loop.interrupt).start()
    loop.run()
    assert io.woken


def test_close_releases_every_fd():
    io = FakeIO({"/dev/input/event1": KBD_CAPS, "/dev/input/event2": MOUSE_CAPS})
    loop = _loop(io)
    loop.close()
    assert {10, 11, WAKE_R, WAKE_W} <= set(io.closed)
    assert io.udev_closed
    assert loop._devices == {}


def test_factory_builds_a_loop_with_the_given_io():
    io = FakeIO({"/dev/input/event1": KBD_CAPS})
    loop = EvdevInputLoop.factory(MagicMock(), io_factory=lambda: io)(MagicMock(), lambda: False)
    assert list(loop._devices) == [10]


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def _grab_setup():
    io = FakeIO({"/dev/input/event4": KBD_CAPS, "/dev/input/event5": MOUSE_CAPS})
    detector = MagicMock()
    detector.active = False
    clock = _Clock()
    loop = _loop(io, detector, clock=clock)
    return io, detector, clock, loop


def _move(io, loop, fd=11):
    io.data[fd] = [_ev(EV_REL, REL_X, 5) + _ev(EV_SYN, SYN_REPORT, 0)]
    loop._read(loop._devices[fd])


def test_grabbed_keyboard_is_warned_about_once(caplog):
    io, detector, clock, loop = _grab_setup()
    io.states[10] = _key_state(29)  # the kernel sees Ctrl held, no event reached us
    _move(io, loop)
    clock.now += GRAB_CHECK_INTERVAL_S
    _move(io, loop)
    assert caplog.text.count("cannot see 'name of /dev/input/event4' (/dev/input/event4)") == 1
    assert 10 in loop._devices
    detector.on_motion.assert_not_called()


def test_grab_check_reads_queued_events_first(caplog):
    io, detector, clock, loop = _grab_setup()
    io.states[10] = _key_state(29)
    io.data[10] = [_ev(EV_KEY, 29, 1)]
    _move(io, loop)
    assert "cannot see" not in caplog.text


def test_grab_check_is_rate_limited():
    io, detector, clock, loop = _grab_setup()
    _move(io, loop)
    io.states[10] = _key_state(29)
    _move(io, loop)
    assert not loop._devices[10].grab_warned
    clock.now += GRAB_CHECK_INTERVAL_S
    _move(io, loop)
    assert loop._devices[10].grab_warned


def test_modifier_reported_by_another_device_is_no_warning(caplog):
    io, detector, clock, loop = _grab_setup()
    io.states[10] = _key_state(29)
    loop._devices[11].pressed.add(29)  # e.g. a remapper's virtual keyboard re-sent it
    _move(io, loop)
    assert "cannot see" not in caplog.text


def test_grab_check_resyncs_a_missed_release():
    io, detector, clock, loop = _grab_setup()
    loop._devices[10].pressed.add(42)
    _move(io, loop)
    assert loop._devices[10].pressed == set()
    detector.on_state.assert_called_with(Modifier.NONE, False)


def test_grab_check_skips_an_unreadable_key_state(caplog):
    io, detector, clock, loop = _grab_setup()
    io.states[10] = OSError("nope")
    _move(io, loop)
    assert "cannot see" not in caplog.text


def test_grab_check_skips_a_keyboard_that_vanished():
    io, detector, clock, loop = _grab_setup()
    io.read_errors[10] = OSError(errno.ENODEV, "gone")
    _move(io, loop)
    assert 10 not in loop._devices


def test_no_grab_check_while_the_gesture_is_held(caplog):
    io, detector, clock, loop = _grab_setup()
    detector.active = True
    detector.on_motion.return_value = None
    io.states[10] = _key_state(29)
    _move(io, loop)
    assert "cannot see" not in caplog.text


def test_open_logs_the_device_count(caplog):
    caplog.set_level(logging.INFO)
    _loop(FakeIO({"/dev/input/event1": KBD_CAPS}))
    assert "reads 1 input devices" in caplog.text
