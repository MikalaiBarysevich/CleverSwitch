import errno
import logging
import os
import threading
from collections import deque
from unittest.mock import MagicMock

import pytest

from cleverswitch.edgeswitch.edge_detector import EdgeDetector
from cleverswitch.edgeswitch.edge_sink import EdgeSink
from cleverswitch.edgeswitch.geometry import Rect
from cleverswitch.edgeswitch.linux import libinput_event as li
from cleverswitch.edgeswitch.linux.libinput_event import LibinputEvent
from cleverswitch.edgeswitch.linux.libinput_loop import OPEN_FLAGS, PERMISSION_HINT, SEAT, LibinputLoop
from cleverswitch.model.config.edge import Edge
from cleverswitch.model.config.modifier import Modifier

LEFTCTRL, LEFTSHIFT, BTN_LEFT = 29, 42, 0x110
KEYBOARD, MOUSE, SWITCH = 1, 2, 3
SCREEN = Rect(0, 0, 1920, 1080)


def added(device, keyboard=False, pointer=False):
    return LibinputEvent(li.DEVICE_ADDED, device=device, keyboard=keyboard, pointer=pointer, name=f"dev{device}")


def removed(device):
    return LibinputEvent(li.DEVICE_REMOVED, device=device)


def key(code, count):
    return LibinputEvent(li.KEYBOARD_KEY, code=code, seat_count=count)


def button(code, count):
    return LibinputEvent(li.POINTER_BUTTON, code=code, seat_count=count)


def motion():
    return LibinputEvent(li.POINTER_MOTION)


def absolute_motion():
    return LibinputEvent(li.POINTER_MOTION_ABSOLUTE)


class FakeLibinput:
    """Opens its paths through open_restricted on creation, like assign_seat, and replays queued events."""

    def __init__(self, seat, open_cb, close_cb, paths=(), events=(), rc=0):
        self.seat = seat
        self.open_cb = open_cb
        self.close_cb = close_cb
        self.events = deque(events)
        self.rcs = deque()
        self.rc = rc
        self.closed = False
        self.opened = [fd for fd in (open_cb(path, os.O_RDWR) for path in paths) if fd >= 0]
        self._r, self._w = os.pipe()
        self.on_dispatch = None

    def fd(self):
        return self._r

    def push(self, *events):
        self.events.extend(events)
        os.write(self._w, b"x")

    def dispatch(self):
        try:
            os.set_blocking(self._r, False)
            os.read(self._r, 64)
        except BlockingIOError:
            pass
        if self.on_dispatch is not None:
            self.on_dispatch()
        return self.rcs.popleft() if self.rcs else self.rc

    def read_event(self):
        return self.events.popleft() if self.events else None

    def close(self):
        self.closed = True
        for fd in self.opened:
            self.close_cb(fd)
        os.close(self._r)
        os.close(self._w)


class FakeOS:
    def __init__(self, denied=(), missing=(), broken=()):
        self.denied, self.missing, self.broken = set(denied), set(missing), set(broken)
        self.opens = []
        self.closed = []
        self._next = 100

    def open(self, path, flags):
        self.opens.append((path, flags))
        if path in self.denied:
            raise PermissionError(errno.EACCES, "denied")
        if path in self.missing:
            raise FileNotFoundError(errno.ENOENT, "gone")
        if path in self.broken:
            raise RuntimeError("unexpected")
        self._next += 1
        return self._next

    def close(self, fd):
        self.closed.append(fd)


class FakeLocator:
    """A Hyprland-style feed: asked per motion burst, no fd of its own."""

    name = "Hyprland"

    def __init__(self, positions=()):
        self.positions = list(positions)
        self.locates = 0
        self.forgets = 0
        self.drains = 0
        self.closed = 0

    def fd(self):
        return None

    def drain(self, _sink):
        self.drains += 1

    def on_motion(self, sink):
        sink.on_motion(self.locate)

    def on_state_changed(self):
        self.forgets += 1

    def close(self):
        self.closed += 1

    def locate(self):
        self.locates += 1
        position = self.positions.pop(0) if self.positions else None
        if position is None:
            raise OSError("Hyprland stopped answering")
        return (*position, SCREEN)


class FakeReportingFeed(FakeLocator):
    """A KWin-style feed: reports edges over its own fd."""

    name = "KWin"

    def __init__(self):
        super().__init__()
        self.reports = deque()
        self._r, self._w = os.pipe()
        os.set_blocking(self._r, False)

    def fd(self):
        return self._r

    def push(self, edges):
        self.reports.append(edges)
        os.write(self._w, b"x")

    def drain(self, sink):
        self.drains += 1
        try:
            os.read(self._r, 64)
        except BlockingIOError:
            pass
        while self.reports:
            sink.on_edges(self.reports.popleft())

    def close(self):
        super().close()
        if self.closed == 1:
            os.close(self._r)
            os.close(self._w)


def _loop(events=(), paths=(), fake_os=None, sink=None, locator=None, rc=0):
    fake_os = fake_os or FakeOS()
    holder = {}

    def binding(seat, open_cb, close_cb):
        holder["li"] = FakeLibinput(seat, open_cb, close_cb, paths, events, rc)
        return holder["li"]

    loop = LibinputLoop(binding, sink or MagicMock(), locator or FakeLocator(), fake_os.open, fake_os.close)
    return loop, holder["li"], fake_os


def _edge_loop(positions, stopping=lambda: False):
    publish = MagicMock()
    detector = EdgeDetector(frozenset({Edge.LEFT}), Modifier.CTRL, 0, clock=lambda: 0.0)
    locator = FakeLocator(positions)
    loop, fake, _ = _loop(sink=EdgeSink(detector, publish, stopping), locator=locator)
    fake.push(added(KEYBOARD, keyboard=True), added(MOUSE, pointer=True), key(LEFTCTRL, 1))
    loop._dispatch()
    return loop, fake, locator, publish


def test_startup_counts_keyboards_and_pointers_only(caplog):
    caplog.set_level(logging.INFO)
    loop, fake, _ = _loop([added(KEYBOARD, keyboard=True), added(MOUSE, pointer=True), added(SWITCH)])
    assert set(loop._devices) == {KEYBOARD, MOUSE}
    assert fake.seat == SEAT
    assert "reads 2 input devices and the cursor position from Hyprland" in caplog.text


def test_failed_binding_closes_the_pipe(monkeypatch):
    pipes = []
    real_pipe = os.pipe

    def tracking_pipe():
        pipes.extend(real_pipe())
        return pipes[0], pipes[1]

    def binding(*_):
        raise OSError("no libinput")

    monkeypatch.setattr(os, "pipe", tracking_pipe)
    with pytest.raises(OSError, match="no libinput"):
        LibinputLoop(binding, MagicMock(), FakeLocator())
    for fd in pipes:
        with pytest.raises(OSError):
            os.fstat(fd)


def test_failed_first_dispatch_closes_and_raises():
    holder = {}

    def binding(seat, open_cb, close_cb):
        holder["li"] = FakeLibinput(seat, open_cb, close_cb, rc=-errno.EIO)
        return holder["li"]

    with pytest.raises(OSError):
        LibinputLoop(binding, MagicMock(), FakeLocator())
    assert holder["li"].closed


def test_open_restricted_opens_read_only_and_maps_errors():
    fake_os = FakeOS(denied={b"/dev/input/event1"}, missing={b"/dev/input/event2"}, broken={b"/dev/input/event3"})
    loop, _, _ = _loop(fake_os=fake_os)
    assert loop._open_restricted(b"/dev/input/event0", os.O_RDWR) == 101
    assert fake_os.opens[-1] == (b"/dev/input/event0", OPEN_FLAGS)
    assert loop._open_restricted(b"/dev/input/event1", os.O_RDWR) == -errno.EACCES
    assert loop._denied == 1
    assert loop._open_restricted(b"/dev/input/event2", os.O_RDWR) == -errno.ENOENT
    assert loop._denied == 1
    assert loop._open_restricted(b"/dev/input/event3", os.O_RDWR) == -errno.EIO


def test_close_restricted_ignores_errors():
    fake_os = FakeOS()
    fake_os.close = MagicMock(side_effect=OSError("bad fd"))
    loop, _, _ = _loop(fake_os=fake_os)
    loop._close_restricted(5)


def test_nothing_readable_warns_once(caplog):
    loop, fake, _ = _loop(paths=[b"/dev/input/event1"], fake_os=FakeOS(denied={b"/dev/input/event1"}))
    loop._denied = 1
    loop._dispatch()
    assert caplog.text.count(PERMISSION_HINT) == 1


def test_refused_node_beside_a_readable_keyboard_is_no_warning(caplog):
    _loop([added(KEYBOARD, keyboard=True)], paths=[b"/dev/input/event1"], fake_os=FakeOS(denied={b"/dev/input/event1"}))
    assert PERMISSION_HINT not in caplog.text


def test_no_devices_and_no_refusal_is_no_warning(caplog):
    _loop()
    assert PERMISSION_HINT not in caplog.text


def test_keys_and_buttons_reach_the_sink():
    sink = MagicMock()
    loop, fake, _ = _loop([added(KEYBOARD, keyboard=True), added(MOUSE, pointer=True)], sink=sink)
    fake.push(key(LEFTCTRL, 1))
    loop._dispatch()
    sink.on_state.assert_called_with(Modifier.CTRL, False)
    fake.push(button(BTN_LEFT, 1), key(LEFTSHIFT, 1))
    loop._dispatch()
    sink.on_state.assert_called_with(Modifier.CTRL | Modifier.SHIFT, True)


def test_untracked_key_does_not_touch_the_sink():
    sink = MagicMock()
    loop, fake, _ = _loop(sink=sink)
    fake.push(key(30, 1))
    loop._dispatch()
    sink.on_state.assert_not_called()


def test_removing_the_last_keyboard_clears_held_modifiers():
    sink = MagicMock()
    loop, fake, _ = _loop([added(KEYBOARD, keyboard=True), added(MOUSE, pointer=True), key(LEFTCTRL, 1)], sink=sink)
    fake.push(button(BTN_LEFT, 1), removed(KEYBOARD))
    loop._dispatch()
    sink.on_state.assert_called_with(Modifier.NONE, True)
    fake.push(removed(MOUSE))
    loop._dispatch()
    sink.on_state.assert_called_with(Modifier.NONE, False)


def test_removing_an_unknown_device_changes_nothing():
    sink = MagicMock()
    loop, fake, _ = _loop(sink=sink)
    fake.push(removed(SWITCH))
    loop._dispatch()
    sink.on_state.assert_not_called()


def test_run_returns_after_interrupt_from_another_thread():
    loop, fake, _ = _loop()
    fake.on_dispatch = lambda: threading.Thread(target=loop.interrupt).start()
    fake.push(motion())
    loop.run()


def test_interrupt_before_run_returns_at_once():
    loop, fake, _ = _loop()
    loop.interrupt()
    fake.push(key(LEFTCTRL, 1))
    loop.run()
    assert fake.events  # nothing was dispatched


def test_interrupted_dispatch_is_retried():
    sink = MagicMock()
    loop, fake, _ = _loop(sink=sink)
    fake.rcs.append(-errno.EINTR)
    fake.push(key(LEFTCTRL, 1))
    loop._dispatch()
    sink.on_state.assert_not_called()
    loop._dispatch()
    sink.on_state.assert_called_with(Modifier.CTRL, False)


def test_dispatch_failure_ends_run():
    loop, fake, _ = _loop()
    fake.rcs.append(-errno.EIO)
    fake.push(motion())
    with pytest.raises(OSError):
        loop.run()


def test_close_releases_libinput_then_the_pipe_and_is_idempotent():
    loop, fake, fake_os = _loop(paths=[b"/dev/input/event0"])
    wake_r = loop._wake_r
    loop.close()
    assert fake.closed
    assert fake_os.closed == [101]
    with pytest.raises(OSError):
        os.fstat(wake_r)
    loop.close()


def test_moving_onto_the_edge_publishes():
    loop, fake, _, publish = _edge_loop([(900, 500), (0, 500)])
    fake.push(motion())
    loop._dispatch()
    publish.assert_not_called()
    fake.push(motion())
    loop._dispatch()
    publish.assert_called_once_with(Edge.LEFT)


def test_an_absolute_pointer_also_triggers_the_cursor_lookup():
    # Tablets and absolute touchscreens emit POINTER_MOTION_ABSOLUTE only, never a relative motion event.
    loop, fake, _, publish = _edge_loop([(900, 500), (0, 500)])
    fake.push(absolute_motion())
    loop._dispatch()
    publish.assert_not_called()
    fake.push(absolute_motion())
    loop._dispatch()
    publish.assert_called_once_with(Edge.LEFT)


def test_cursor_already_on_the_edge_does_not_publish():
    loop, fake, _, publish = _edge_loop([(0, 500), (0, 500)])
    for _ in range(2):
        fake.push(motion())
        loop._dispatch()
    publish.assert_not_called()


def test_locates_once_per_burst():
    loop, fake, locator, _ = _edge_loop([(900, 500)])
    fake.push(motion(), motion(), motion())
    loop._dispatch()
    assert locator.locates == 1


def test_hyprland_is_not_asked_without_the_gesture():
    loop, fake, locator, _ = _edge_loop([(900, 500)])
    fake.push(key(LEFTCTRL, 0), motion())
    loop._dispatch()
    assert locator.locates == 0


def test_a_modifier_change_is_forwarded_to_the_sink():
    loop, fake, locator, _ = _edge_loop([])
    fake.push(key(LEFTCTRL, 0))
    loop._dispatch()
    assert locator.locates == 0


def test_stopping_blocks_publishing():
    loop, fake, _, publish = _edge_loop([(900, 500), (0, 500)], stopping=lambda: True)
    for _ in range(2):
        fake.push(motion())
        loop._dispatch()
    publish.assert_not_called()


def test_hyprland_that_stops_answering_ends_run():
    loop, fake, _, _ = _edge_loop([])
    fake.push(motion())
    with pytest.raises(OSError, match="stopped answering"):
        loop.run()


def test_a_reporting_feed_is_polled_and_drained():
    detector = EdgeDetector(frozenset({Edge.LEFT}), Modifier.CTRL, 0, clock=lambda: 0.0)
    feed = FakeReportingFeed()
    loop = None
    publish = MagicMock(side_effect=lambda _edge: threading.Thread(target=loop.interrupt).start())
    loop, fake, _ = _loop(sink=EdgeSink(detector, publish, lambda: False), locator=feed)
    fake.push(added(KEYBOARD, keyboard=True), key(LEFTCTRL, 1))
    loop._dispatch()
    feed.push(frozenset())
    feed.push(frozenset({Edge.LEFT}))
    loop.run()
    publish.assert_called_once_with(Edge.LEFT)


def test_start_up_names_the_feed(caplog):
    caplog.set_level(logging.INFO)
    _loop(locator=FakeReportingFeed())
    assert "cursor position from KWin" in caplog.text


def test_feed_is_drained_even_when_libinput_asks_to_retry():
    feed = FakeReportingFeed()
    sink = MagicMock()
    loop, fake, _ = _loop(sink=sink, locator=feed)
    fake.rcs.append(-errno.EAGAIN)
    feed.push(frozenset({Edge.LEFT}))
    loop._dispatch()
    sink.on_edges.assert_called_once_with(frozenset({Edge.LEFT}))


def test_close_closes_the_feed_and_a_failed_start_too():
    feed = FakeLocator()
    loop, _, _ = _loop(locator=feed)
    loop.close()
    assert feed.closed == 1

    feed = FakeLocator()

    def binding(*_):
        raise OSError("no libinput")

    with pytest.raises(OSError):
        LibinputLoop(binding, MagicMock(), feed)
    assert feed.closed == 1
