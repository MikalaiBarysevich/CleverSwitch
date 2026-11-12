import struct

from cleverswitch.edgeswitch.linux.input_event import (
    EV_KEY,
    EVENT_SIZE,
    held_modifiers,
    parse_events,
    pressed_keys,
)
from cleverswitch.model.config.modifier import Modifier


def _event(etype, code, value):
    return struct.pack("llHHi", 1, 2, etype, code, value)


def test_parse_events_decodes_and_ignores_a_partial_tail():
    data = _event(EV_KEY, 29, 1) + _event(2, 0, -5) + b"\x00" * (EVENT_SIZE - 1)
    assert parse_events(data) == [(EV_KEY, 29, 1), (2, 0, -5)]


def test_pressed_keys_reads_tracked_bits_only():
    state = bytearray(96)
    for code in (29, 126, 0x110, 30):
        state[code // 8] |= 1 << (code % 8)
    assert pressed_keys(bytes(state)) == {29, 126, 0x110}


def test_pressed_keys_tolerates_a_short_buffer():
    assert pressed_keys(b"\x00" * 4) == set()


def test_held_modifiers_merges_left_and_right():
    assert held_modifiers({29, 97, 100, 0x110}) == Modifier.CTRL | Modifier.ALT
    assert held_modifiers({42, 125}) == Modifier.SHIFT | Modifier.META
