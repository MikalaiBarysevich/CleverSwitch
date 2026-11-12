from unittest.mock import MagicMock

import pytest

from cleverswitch.edgeswitch.edge_detector import EdgeDetector
from cleverswitch.edgeswitch.windows.raw_input_loop import RawInputLoop
from cleverswitch.edgeswitch.windows.user32 import WM_INPUT
from cleverswitch.model.config.edge import Edge
from cleverswitch.model.config.modifier import Modifier

WM_TIMER = 0x0113
CTRL = 0x11


class FakeUser32:
    """Replays (result, message, pending_after, keys, cursor) steps; WM_QUIT when the script ends."""

    def __init__(self, steps=(), screen=(0, 0, 1920, 1080), fail_open=None):
        self.steps = list(steps)
        self.screen = screen
        self.fail_open = fail_open
        self.calls = []
        self.keys = set()
        self.cursor = (900, 500)
        self._pending = False
        self.cursor_reads = 0

    def use_per_monitor_dpi(self):
        self.calls.append("dpi")

    def current_thread_id(self):
        return 77

    def open_sink_window(self):
        self.calls.append("open")
        if self.fail_open:
            raise self.fail_open

    def close_sink_window(self):
        self.calls.append("close")

    def next_message(self):
        if not self.steps:
            return 0, 0
        result, message, pending, keys, cursor = self.steps.pop(0)
        self._pending = pending
        self.keys = set(keys)
        self.cursor = cursor
        return result, message

    def dispatch(self):
        self.calls.append("dispatch")

    def raw_input_pending(self):
        return self._pending

    def post_quit(self, thread_id):
        self.calls.append(("quit", thread_id))

    def cursor_pos(self):
        self.cursor_reads += 1
        return self.cursor

    def key_down(self, vk):
        return vk in self.keys

    def virtual_screen(self):
        return self.screen


def _loop(fake):
    detector = EdgeDetector(frozenset({Edge.LEFT}), Modifier.CTRL, 0, clock=lambda: 0.0)
    publish = MagicMock()
    build = RawInputLoop.factory(lambda: fake, detector)
    return build(publish, lambda: False), publish


def _input(keys=(), cursor=(900, 500), pending=False):
    return (1, WM_INPUT, pending, keys, cursor)


def test_sets_dpi_awareness_before_opening_the_window():
    fake = FakeUser32()
    _loop(fake)
    assert fake.calls == ["dpi", "open"]


def test_window_failure_propagates():
    with pytest.raises(OSError, match="denied"):
        _loop(FakeUser32(fail_open=OSError("denied")))


def test_ctrl_and_move_onto_the_edge_publishes():
    fake = FakeUser32([_input({CTRL}, (900, 500)), _input({CTRL}, (0, 500))])
    loop, publish = _loop(fake)

    loop.run()

    publish.assert_called_once_with(Edge.LEFT)


def test_a_burst_is_evaluated_once_when_the_queue_drains():
    fake = FakeUser32([_input({CTRL}, (900, 500), pending=True), _input({CTRL}, (0, 500), pending=True)])
    loop, publish = _loop(fake)

    loop.run()

    assert fake.cursor_reads == 0
    publish.assert_not_called()


def test_cursor_is_not_read_without_the_modifier():
    fake = FakeUser32([_input((), (900, 500)), _input((), (0, 500))])
    loop, publish = _loop(fake)

    loop.run()

    assert fake.cursor_reads == 0
    publish.assert_not_called()


def test_non_input_messages_are_dispatched_only():
    fake = FakeUser32([(1, WM_TIMER, False, {CTRL}, (900, 500))])
    loop, _ = _loop(fake)

    loop.run()

    assert fake.calls.count("dispatch") == 1
    assert fake.cursor_reads == 0


def test_held_button_blocks():
    fake = FakeUser32([_input({CTRL, 0x01}, (900, 500)), _input({CTRL, 0x01}, (0, 500))])
    loop, publish = _loop(fake)
    loop.run()
    publish.assert_not_called()


def test_secure_desktop_or_empty_screen_is_skipped():
    fake = FakeUser32([_input({CTRL}, None), _input({CTRL}, (900, 500))], screen=(0, 0, 0, 0))
    loop, publish = _loop(fake)
    loop.run()
    publish.assert_not_called()


def test_get_message_error_raises():
    loop, _ = _loop(FakeUser32([(-1, 0, False, (), None)]))
    with pytest.raises(OSError, match="GetMessageW"):
        loop.run()


def test_interrupt_posts_quit_to_the_loop_thread_and_close_destroys_the_window():
    fake = FakeUser32()
    loop, _ = _loop(fake)
    loop.interrupt()
    loop.close()
    assert ("quit", 77) in fake.calls
    assert fake.calls[-1] == "close"
