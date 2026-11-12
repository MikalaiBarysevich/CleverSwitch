from __future__ import annotations

from .input_event import BTN_LEFT, KEY_LEFTCTRL, REL_X, REL_Y

# sysfs capability bitmaps are space-separated hex words, most significant first.
_WORD_BITS = 64


def has_bit(bitmap: str, bit: int, word_bits: int = _WORD_BITS) -> bool:
    words = bitmap.split()
    index = len(words) - 1 - bit // word_bits
    if index < 0:
        return False
    try:
        return bool(int(words[index], 16) & (1 << (bit % word_bits)))
    except ValueError:
        return False


def is_keyboard(key_caps: str) -> bool:
    return has_bit(key_caps, KEY_LEFTCTRL)


def is_pointer(key_caps: str, rel_caps: str) -> bool:
    return has_bit(rel_caps, REL_X) and has_bit(rel_caps, REL_Y) and has_bit(key_caps, BTN_LEFT)
