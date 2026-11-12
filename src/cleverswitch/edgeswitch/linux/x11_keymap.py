from __future__ import annotations

from ...model.config.modifier import Modifier

# Modifiers come from the keymap, not the pointer's modifier mask: which of Mod1..Mod5 means alt or
# super depends on the server's modifier mapping.
MODIFIER_KEYSYMS = {
    0xFFE3: Modifier.CTRL,  # Control_L
    0xFFE4: Modifier.CTRL,  # Control_R
    0xFFE1: Modifier.SHIFT,  # Shift_L
    0xFFE2: Modifier.SHIFT,  # Shift_R
    0xFFE9: Modifier.ALT,  # Alt_L
    0xFFEA: Modifier.ALT,  # Alt_R
    0xFE03: Modifier.ALT,  # ISO_Level3_Shift (AltGr layouts)
    0xFFE7: Modifier.META,  # Meta_L
    0xFFE8: Modifier.META,  # Meta_R
    0xFFEB: Modifier.META,  # Super_L
    0xFFEC: Modifier.META,  # Super_R
}
# Button1..Button3; 4 and 5 are the scroll wheel, down only for an instant.
BUTTON_MASK = (1 << 8) | (1 << 9) | (1 << 10)


def modifier_keycodes(keysyms_per_keycode: int, first_keycode: int, keysyms: list[int]) -> dict[int, Modifier]:
    result: dict[int, Modifier] = {}
    if keysyms_per_keycode <= 0:
        return result
    for index, keysym in enumerate(keysyms):
        modifier = MODIFIER_KEYSYMS.get(keysym)
        if modifier is not None:
            keycode = first_keycode + index // keysyms_per_keycode
            result[keycode] = result.get(keycode, Modifier.NONE) | modifier
    return result


def modifiers_from_keymap(keymap: bytes, keycodes: dict[int, Modifier]) -> Modifier:
    result = Modifier.NONE
    for keycode, modifier in keycodes.items():
        if keymap[keycode // 8] & (1 << (keycode % 8)):
            result |= modifier
    return result
