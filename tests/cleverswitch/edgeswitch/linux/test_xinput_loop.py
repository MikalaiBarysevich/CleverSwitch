import os
import threading
from unittest.mock import MagicMock

import pytest

from cleverswitch.edgeswitch.edge_detector import EdgeDetector
from cleverswitch.edgeswitch.geometry import Rect
from cleverswitch.edgeswitch.linux import x11_events
from cleverswitch.edgeswitch.linux.xinput_loop import XInputLoop
from cleverswitch.model.config.edge import Edge
from cleverswitch.model.config.modifier import Modifier

from .test_x11_events import OPCODE, configure, generic, mapping
from .test_x11_keymap import KEYSYMS, keymap

ROOT = 0x1EE
CTRL = 9
SHIFT = 12
LEFT_BUTTON = 1 << 8


class FakeXcb:
    def __init__(self, fail_enable=None):
        self.fail_enable = fail_enable
        self.root = ROOT
        self.events = []
        self.keys = set()
        self.pointer = (900, 500, 0)
        self.geometry = (0, 0, 1920, 1080)
        self.mapping = (2, 8, KEYSYMS)
        self.error = False
        self.closed = False
        self.pointer_reads = 0
        self.on_empty = None
        self._fd_r, self._fd_w = os.pipe()

    def enable_raw_events(self):
        if self.fail_enable:
            raise self.fail_enable
        return OPCODE

    def fd(self):
        return self._fd_r

    def flush(self):
        pass

    def next_event(self):
        if self.events:
            return self.events.pop(0)
        if self.on_empty is not None:
            self.on_empty()
        return None

    def has_error(self):
        return self.error

    def query_keymap(self):
        return keymap(*self.keys)

    def query_pointer(self):
        self.pointer_reads += 1
        return self.pointer

    def root_geometry(self):
        return self.geometry

    def keyboard_mapping(self):
        return self.mapping

    def close(self):
        self.closed = True
        os.close(self._fd_r)
        os.close(self._fd_w)


def _loop(fake, edges=frozenset({Edge.LEFT}), stopping=lambda: False):
    detector = EdgeDetector(edges, Modifier.CTRL, 0, clock=lambda: 0.0)
    publish = MagicMock()
    return XInputLoop.factory(lambda: fake, detector)(publish, stopping), publish


def _press(fake, keycode):
    fake.keys.add(keycode)
    fake.events.append(generic(x11_events.XI_RAW_KEY_PRESS, keycode))


def _move(fake, x, y):
    fake.pointer = (x, y, fake.pointer[2])
    fake.events.append(generic(x11_events.XI_RAW_MOTION, 0))


def test_ctrl_and_moving_onto_the_left_edge_publishes():
    fake = FakeXcb()
    loop, publish = _loop(fake)
    _press(fake, CTRL)
    _move(fake, 900, 500)
    loop._drain()
    _move(fake, 0, 500)
    loop._drain()
    publish.assert_called_once_with(Edge.LEFT)


def test_pressing_ctrl_already_on_the_edge_does_nothing():
    fake = FakeXcb()
    fake.pointer = (0, 500, 0)
    loop, publish = _loop(fake)
    _press(fake, CTRL)
    _move(fake, 0, 500)
    loop._drain()
    publish.assert_not_called()


def test_held_button_blocks_the_switch():
    fake = FakeXcb()
    loop, publish = _loop(fake)
    _press(fake, CTRL)
    fake.pointer = (900, 500, LEFT_BUTTON)
    fake.events.append(generic(x11_events.XI_RAW_BUTTON_PRESS, 1))
    _move(fake, 0, 500)
    loop._drain()
    publish.assert_not_called()


def test_scroll_wheel_does_not_reread_state():
    fake = FakeXcb()
    loop, _ = _loop(fake)
    reads = fake.pointer_reads
    fake.events.append(generic(x11_events.XI_RAW_BUTTON_PRESS, 4))
    loop._drain()
    assert fake.pointer_reads == reads


def test_non_modifier_key_does_not_reread_state():
    fake = FakeXcb()
    loop, _ = _loop(fake)
    reads = fake.pointer_reads
    fake.events.append(generic(x11_events.XI_RAW_KEY_PRESS, 8))
    loop._drain()
    assert fake.pointer_reads == reads


def test_motion_without_the_modifier_reads_no_pointer():
    fake = FakeXcb()
    loop, _ = _loop(fake)
    reads = fake.pointer_reads
    _move(fake, 0, 500)
    loop._drain()
    assert fake.pointer_reads == reads


def test_extra_modifier_blocks_the_switch():
    fake = FakeXcb()
    loop, publish = _loop(fake)
    _press(fake, CTRL)
    _press(fake, SHIFT)
    _move(fake, 0, 500)
    loop._drain()
    publish.assert_not_called()


def test_root_resize_moves_the_right_edge():
    fake = FakeXcb()
    loop, publish = _loop(fake, edges=frozenset({Edge.RIGHT}))
    fake.events.append(configure(ROOT, 0, 0, 3840, 1080))
    _press(fake, CTRL)
    _move(fake, 1919, 500)
    loop._drain()
    publish.assert_not_called()
    _move(fake, 3839, 500)
    loop._drain()
    publish.assert_called_once_with(Edge.RIGHT)


def test_configure_of_another_window_is_ignored():
    fake = FakeXcb()
    loop, _ = _loop(fake)
    fake.events.append(configure(ROOT + 1, 0, 0, 10, 10))
    loop._drain()
    assert loop._bounds == Rect(0, 0, 1920, 1080)


def test_mapping_change_reloads_modifier_keycodes():
    fake = FakeXcb()
    loop, publish = _loop(fake)
    fake.mapping = (1, 8, [0, 0, 0, 0, 0, 0, 0, 0, 0xFFE3])  # Control_L moves to keycode 16
    fake.keys.add(16)
    fake.events.append(mapping(x11_events.MAPPING_KEYBOARD))
    _move(fake, 900, 500)
    loop._drain()
    _move(fake, 0, 500)
    loop._drain()
    assert loop._keycodes == {16: Modifier.CTRL}
    publish.assert_called_once_with(Edge.LEFT)


def test_pointer_mapping_change_keeps_keycodes():
    fake = FakeXcb()
    loop, _ = _loop(fake)
    before = loop._keycodes
    fake.mapping = None
    fake.events.append(mapping(2))  # MappingPointer
    loop._drain()
    assert loop._keycodes == before


def test_no_keyboard_mapping_means_no_modifiers():
    fake = FakeXcb()
    fake.mapping = None
    loop, _ = _loop(fake)
    assert loop._keycodes == {}


def test_missing_replies_change_nothing():
    fake = FakeXcb()
    fake.geometry = None
    loop, publish = _loop(fake)
    assert loop._bounds is None
    fake.query_keymap = lambda: None
    _press(fake, CTRL)
    loop._drain()
    fake.query_pointer = lambda: None
    _move(fake, 0, 500)
    loop._drain()
    publish.assert_not_called()


def test_lost_connection_raises():
    fake = FakeXcb()
    loop, _ = _loop(fake)
    fake.error = True
    with pytest.raises(OSError, match="lost"):
        loop.run()


def test_interrupt_before_run_returns_at_once():
    fake = FakeXcb()
    loop, _ = _loop(fake)
    loop.interrupt()
    loop.run()


def test_interrupt_from_another_thread_wakes_run():
    fake = FakeXcb()
    loop, publish = _loop(fake)
    _press(fake, CTRL)
    _move(fake, 900, 500)
    steps = [lambda: None, lambda: _move(fake, 0, 500), lambda: threading.Thread(target=loop.interrupt).start()]
    fake.on_empty = lambda: steps.pop(0)() if steps else None
    os.write(fake._fd_w, b"\0")  # the X socket stays readable, so each step is its own burst
    loop.run()
    publish.assert_called_once_with(Edge.LEFT)


def test_close_releases_pipe_and_connection():
    fake = FakeXcb()
    loop, _ = _loop(fake)
    wake_r = loop._wake_r
    loop.close()
    assert fake.closed
    with pytest.raises(OSError):
        os.fstat(wake_r)


def test_failed_setup_closes_the_connection():
    fake = FakeXcb(fail_enable=OSError("no XInput"))
    with pytest.raises(OSError, match="no XInput"):
        _loop(fake)
    assert fake.closed
