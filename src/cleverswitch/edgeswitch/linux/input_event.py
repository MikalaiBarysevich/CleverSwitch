from __future__ import annotations

import struct

from ...model.config.modifier import Modifier

EV_SYN = 0x00
EV_KEY = 0x01
EV_REL = 0x02
SYN_REPORT = 0
SYN_DROPPED = 3
REL_X = 0x00
REL_Y = 0x01

KEY_LEFTCTRL = 29
BTN_LEFT = 0x110

MODIFIER_KEYS = {
    29: Modifier.CTRL,  # KEY_LEFTCTRL
    97: Modifier.CTRL,  # KEY_RIGHTCTRL
    42: Modifier.SHIFT,  # KEY_LEFTSHIFT
    54: Modifier.SHIFT,  # KEY_RIGHTSHIFT
    56: Modifier.ALT,  # KEY_LEFTALT
    100: Modifier.ALT,  # KEY_RIGHTALT
    125: Modifier.META,  # KEY_LEFTMETA
    126: Modifier.META,  # KEY_RIGHTMETA
}
BUTTONS = frozenset({0x110, 0x111, 0x112})  # BTN_LEFT, BTN_RIGHT, BTN_MIDDLE
TRACKED_KEYS = frozenset(MODIFIER_KEYS) | BUTTONS

# struct input_event: struct timeval time; __u16 type; __u16 code; __s32 value
_EVENT = struct.Struct("llHHi")
EVENT_SIZE = _EVENT.size


def parse_events(data: bytes) -> list[tuple[int, int, int]]:
    usable = len(data) - len(data) % EVENT_SIZE
    return [(etype, code, value) for _s, _us, etype, code, value in _EVENT.iter_unpack(data[:usable])]


def pressed_keys(key_state: bytes) -> set[int]:
    return {code for code in TRACKED_KEYS if code // 8 < len(key_state) and key_state[code // 8] & (1 << (code % 8))}


def held_modifiers(pressed: set[int]) -> Modifier:
    result = Modifier.NONE
    for code in pressed:
        result |= MODIFIER_KEYS.get(code, Modifier.NONE)
    return result
