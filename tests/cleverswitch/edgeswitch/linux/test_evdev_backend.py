import errno
import logging
import struct
import threading
from unittest.mock import MagicMock

import pytest

from cleverswitch.edgeswitch.linux import evdev_backend
from cleverswitch.edgeswitch.linux.evdev_backend import EvdevEdgeBackend
from cleverswitch.edgeswitch.linux.input_event import EV_KEY, EV_REL, EV_SYN, REL_X, REL_Y, SYN_DROPPED, SYN_REPORT
from cleverswitch.errors.errors import EdgeSwitchError
from cleverswitch.event.edge_touched_event import EdgeTouchedEvent
from cleverswitch.model.config.edge import Edge
from cleverswitch.model.config.modifier import Modifier
from cleverswitch.topic.topic import Topic

KBD_CAPS = ("20000000", "0")  # bit 29 = KEY_LEFTCTRL
MOUSE_CAPS = ("1f0000 0 0 0 0", "3")  # BTN_LEFT.., REL_X|REL_Y
OTHER_CAPS = ("0", "0")


def _ev(etype, code, value):
    return struct.pack("llHHi", 0, 0, etype, code, value)


def _key_state(*codes):
    state = bytearray(96)
    for code in codes:
        state[code // 8] |= 1 << (code % 8)
    return bytes(state)


class FakeIO:
    def __init__(self, nodes):
        self.nodes = dict(nodes)  # node -> caps
        self.denied = set()
        self.broken = set()
        self.fds = {}
        self.data = {}
        self.read_errors = {}
        self.states = {}
        self.closed = []
        self._next_fd = 10

    def list_nodes(self):
        return list(self.nodes)

    def read_caps(self, node):
        return self.nodes[node]

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

    def pipe(self):
        return 98, 99

    def wake(self, fd):
        pass

    def poll(self, fds, _timeout_ms):
        return [fd for fd in fds if self.data.get(fd) or fd in self.read_errors]


def _topics():
    topics = MagicMock()
    topics.edge = MagicMock(spec=Topic)
    return topics


def _backend(io, detector=None, topics=None, clock=lambda: 0.0):
    return EvdevEdgeBackend(detector or MagicMock(), topics or _topics(), io_factory=lambda: io, clock=clock)


def test_scan_opens_keyboards_and_mice_only():
    io = FakeIO({"/dev/input/event1": KBD_CAPS, "/dev/input/event2": MOUSE_CAPS, "/dev/input/event3": OTHER_CAPS})
    backend = _backend(io)

    assert backend._scan() == (2, 0)
    assert set(io.fds) == {"/dev/input/event1", "/dev/input/event2"}
    assert backend._scan() == (0, 0)


def test_start_without_permission_raises_with_hint():
    io = FakeIO({"/dev/input/event1": KBD_CAPS})
    io.denied.add("/dev/input/event1")

    with pytest.raises(EdgeSwitchError, match="input' group"):
        _backend(io).start()


def test_start_with_nothing_found_keeps_looking(caplog):
    caplog.set_level(logging.INFO)
    backend = _backend(FakeIO({}))
    backend.start()
    backend.stop()
    assert "keep looking" in caplog.text


def test_busy_device_is_skipped():
    io = FakeIO({"/dev/input/event1": KBD_CAPS})
    io.broken.add("/dev/input/event1")
    assert _backend(io)._scan() == (0, 0)


def test_initial_key_state_is_reported():
    io = FakeIO({"/dev/input/event1": KBD_CAPS})
    io.states[10] = _key_state(29)
    detector = MagicMock()

    _backend(io, detector)._scan()

    detector.on_state.assert_called_with(Modifier.CTRL, False)


def test_unreadable_key_state_counts_as_nothing_pressed():
    io = FakeIO({"/dev/input/event1": KBD_CAPS})
    io.states[10] = OSError("nope")
    detector = MagicMock()

    _backend(io, detector)._scan()

    detector.on_state.assert_called_with(Modifier.NONE, False)


def test_key_and_motion_events_drive_the_detector():
    io = FakeIO({"/dev/input/event1": KBD_CAPS, "/dev/input/event2": MOUSE_CAPS})
    detector = MagicMock()
    detector.on_motion.return_value = Edge.RIGHT
    topics = _topics()
    backend = _backend(io, detector, topics)
    backend._scan()
    kbd, mouse = backend._devices[10], backend._devices[11]

    io.data[10] = [_ev(EV_KEY, 97, 1) + _ev(EV_SYN, SYN_REPORT, 0)]
    backend._read(kbd)
    detector.on_state.assert_called_with(Modifier.CTRL, False)

    io.data[11] = [
        _ev(EV_KEY, 0x110, 1)
        + _ev(EV_REL, REL_X, 7)
        + _ev(EV_REL, REL_Y, -2)
        + _ev(EV_REL, REL_X, 3)
        + _ev(EV_SYN, SYN_REPORT, 0)
        + _ev(EV_SYN, SYN_REPORT, 0)
    ]
    backend._read(mouse)
    detector.on_state.assert_called_with(Modifier.CTRL, True)
    detector.on_motion.assert_called_once_with(10, -2)
    topics.edge.publish.assert_called_once_with(EdgeTouchedEvent(slot=0, pid=0, edge=Edge.RIGHT))

    io.data[10] = [_ev(EV_KEY, 97, 0)]
    backend._read(kbd)
    detector.on_state.assert_called_with(Modifier.NONE, True)


def test_untracked_keys_are_ignored():
    io = FakeIO({"/dev/input/event1": KBD_CAPS})
    detector = MagicMock()
    backend = _backend(io, detector)
    backend._scan()
    detector.reset_mock()

    io.data[10] = [_ev(EV_KEY, 30, 1)]
    backend._read(backend._devices[10])

    detector.on_state.assert_not_called()


def test_motion_without_publishable_edge_publishes_nothing():
    io = FakeIO({"/dev/input/event2": MOUSE_CAPS})
    detector = MagicMock()
    detector.on_motion.return_value = None
    topics = _topics()
    backend = _backend(io, detector, topics)
    backend._scan()

    io.data[10] = [_ev(EV_REL, REL_X, 5) + _ev(EV_SYN, SYN_REPORT, 0)]
    backend._read(backend._devices[10])

    topics.edge.publish.assert_not_called()


def test_dropped_events_resync_key_state():
    io = FakeIO({"/dev/input/event1": KBD_CAPS})
    detector = MagicMock()
    backend = _backend(io, detector)
    backend._scan()
    device = backend._devices[10]
    device.dx = 50

    io.states[10] = _key_state(29)
    io.data[10] = [_ev(EV_SYN, SYN_DROPPED, 0)]
    backend._read(device)

    assert device.dx == 0
    detector.on_state.assert_called_with(Modifier.CTRL, False)


@pytest.mark.parametrize("error", [OSError(errno.ENODEV, "gone"), OSError(errno.EIO, "io")])
def test_read_failure_drops_device_and_its_keys(error):
    io = FakeIO({"/dev/input/event1": KBD_CAPS})
    io.states[10] = _key_state(29)
    detector = MagicMock()
    backend = _backend(io, detector)
    backend._scan()

    io.read_errors[10] = error
    backend._read(backend._devices[10])

    assert backend._devices == {}
    assert 10 in io.closed
    detector.on_state.assert_called_with(Modifier.NONE, False)


def test_thread_reads_rescans_and_closes_everything_on_stop(mocker):
    mocker.patch.object(evdev_backend, "RESCAN_INTERVAL_S", 0.0)
    io = FakeIO({"/dev/input/event1": KBD_CAPS})
    seen = threading.Event()
    detector = MagicMock()
    detector.on_state.side_effect = lambda mods, _b: seen.set() if mods == Modifier.SHIFT else None
    backend = _backend(io, detector, clock=lambda: 1.0)
    backend.start()

    io.nodes["/dev/input/event2"] = KBD_CAPS
    io.data[10] = [_ev(EV_KEY, 42, 1)]
    assert seen.wait(2)
    backend.stop()

    assert "/dev/input/event2" in io.fds
    assert {10, 11, 98, 99} <= set(io.closed)


def test_stop_without_start_is_a_no_op():
    _backend(FakeIO({})).stop()
