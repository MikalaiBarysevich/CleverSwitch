from cleverswitch.edgeswitch.linux.x11_keymap import modifier_keycodes, modifiers_from_keymap
from cleverswitch.model.config.modifier import Modifier

# Two keysyms per keycode, starting at keycode 8.
KEYSYMS = [
    0x61,
    0x41,  # 8: a A
    0xFFE3,
    0,  # 9: Control_L
    0xFFE9,
    0xFFE7,  # 10: Alt_L Meta_L
    0xFFEB,
    0,  # 11: Super_L
    0xFFE2,
    0,  # 12: Shift_R
    0xFE03,
    0,  # 13: ISO_Level3_Shift
]


def keymap(*keycodes):
    keys = bytearray(32)
    for keycode in keycodes:
        keys[keycode // 8] |= 1 << (keycode % 8)
    return bytes(keys)


def test_modifier_keycodes_resolves_every_column():
    assert modifier_keycodes(2, 8, KEYSYMS) == {
        9: Modifier.CTRL,
        10: Modifier.ALT | Modifier.META,
        11: Modifier.META,
        12: Modifier.SHIFT,
        13: Modifier.ALT,
    }


def test_modifier_keycodes_with_no_columns_is_empty():
    assert modifier_keycodes(0, 8, KEYSYMS) == {}


def test_modifiers_from_keymap():
    keycodes = {9: Modifier.CTRL, 11: Modifier.META, 37: Modifier.CTRL}
    assert modifiers_from_keymap(keymap(37, 11), keycodes) == Modifier.CTRL | Modifier.META
    assert modifiers_from_keymap(keymap(8), keycodes) == Modifier.NONE
