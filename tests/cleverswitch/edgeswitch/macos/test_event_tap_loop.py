from unittest.mock import MagicMock

import pytest

from cleverswitch.edgeswitch.edge_detector import EdgeDetector
from cleverswitch.edgeswitch.macos.event_tap_loop import EventTapLoop
from cleverswitch.edgeswitch.macos.quartz import MOUSE_MOVED, TAP_DISABLED_BY_TIMEOUT
from cleverswitch.model.config.edge import Edge
from cleverswitch.model.config.modifier import Modifier

FLAGS_CHANGED = 12
CTRL_FLAG = 0x00040000


class FakeQuartz:
    """Events are (type, flags, location); run() delivers the queued batch then returns."""

    def __init__(self, granted=True, tap_error=None, reenable=True):
        self.granted = granted
        self.tap_error = tap_error
        self.reenable = reenable
        self.handler = None
        self.batches = []
        self.buttons = set()
        self.displays = [(0, 0, 1512, 982), (-1920, 0, 1920, 1080)]
        self.calls = []
        self.loop = None
        self.bounds_reads = 0

    def listen_access_granted(self):
        return self.granted

    def open_tap(self, handler):
        if self.tap_error:
            raise self.tap_error
        self.handler = handler

    def run(self):
        self.calls.append("run")
        batch = self.batches.pop(0) if self.batches else []
        for event in batch:
            self.handler(event[0], event)
        if not self.batches:
            self.loop._interrupted = True

    def wake_stop(self):
        self.calls.append("wake")

    def stop_run(self):
        self.calls.append("stop_run")

    def reenable_tap(self):
        self.calls.append("reenable")
        return self.reenable

    def event_flags(self, event):
        return event[1]

    def event_location(self, event):
        return event[2]

    def button_down(self, button):
        return button in self.buttons

    def display_bounds(self):
        self.bounds_reads += 1
        return self.displays

    def close_tap(self):
        self.calls.append("close")


def _loop(fake):
    detector = EdgeDetector(frozenset({Edge.LEFT}), Modifier.CTRL, 0, clock=lambda: 0.0)
    publish = MagicMock()
    loop = EventTapLoop.factory(lambda: fake, detector)(publish, lambda: False)
    fake.loop = loop
    return loop, publish


def test_missing_input_monitoring_fails_with_hint():
    with pytest.raises(PermissionError, match="Input Monitoring"):
        _loop(FakeQuartz(granted=False))


def test_tap_that_cannot_be_created_fails_with_hint():
    with pytest.raises(PermissionError, match="Input Monitoring"):
        _loop(FakeQuartz(tap_error=PermissionError("cannot create")))


def test_ctrl_and_move_onto_the_left_edge_of_the_desktop_publishes():
    fake = FakeQuartz()
    loop, publish = _loop(fake)
    fake.batches = [
        [(FLAGS_CHANGED, CTRL_FLAG, None), (MOUSE_MOVED, CTRL_FLAG, (0, 500)), (MOUSE_MOVED, CTRL_FLAG, (-1920, 500))]
    ]

    loop.run()

    publish.assert_called_once_with(Edge.LEFT)


def test_location_and_bounds_are_read_only_while_held():
    fake = FakeQuartz()
    loop, publish = _loop(fake)
    fake.batches = [[(MOUSE_MOVED, 0, (100, 100)), (MOUSE_MOVED, 0, (-1920, 100))]]

    loop.run()

    assert fake.bounds_reads == 0
    publish.assert_not_called()


def test_flags_changed_does_not_read_the_location():
    fake = FakeQuartz()
    loop, _ = _loop(fake)
    fake.batches = [[(FLAGS_CHANGED, CTRL_FLAG, None)]]
    loop.run()
    assert fake.bounds_reads == 0


def test_held_button_blocks():
    fake = FakeQuartz()
    fake.buttons = {0}
    loop, publish = _loop(fake)
    fake.batches = [[(MOUSE_MOVED, CTRL_FLAG, (0, 500)), (MOUSE_MOVED, CTRL_FLAG, (-1920, 500))]]
    loop.run()
    publish.assert_not_called()


def test_disabled_tap_is_reenabled():
    fake = FakeQuartz()
    loop, _ = _loop(fake)
    fake.batches = [[(TAP_DISABLED_BY_TIMEOUT, 0, None)]]
    loop.run()
    assert "reenable" in fake.calls
    assert "stop_run" not in fake.calls


def test_tap_that_stays_disabled_ends_the_loop():
    fake = FakeQuartz(reenable=False)
    loop, _ = _loop(fake)
    fake.batches = [[(TAP_DISABLED_BY_TIMEOUT, 0, None)], []]
    with pytest.raises(PermissionError, match="disabled"):
        loop.run()
    assert "stop_run" in fake.calls


def test_handler_error_is_logged_once_and_swallowed(caplog):
    fake = FakeQuartz()
    loop, _ = _loop(fake)
    fake.event_flags = MagicMock(side_effect=ValueError("bad event"))
    fake.batches = [[(MOUSE_MOVED, 0, (0, 0)), (MOUSE_MOVED, 0, (0, 0))]]
    loop.run()
    assert caplog.text.count("bad event") == 1


def test_interrupt_is_sticky_and_close_releases_the_tap():
    fake = FakeQuartz()
    loop, _ = _loop(fake)
    loop.interrupt()
    loop.run()
    loop.close()
    assert "run" not in fake.calls
    assert fake.calls == ["wake", "close"]
