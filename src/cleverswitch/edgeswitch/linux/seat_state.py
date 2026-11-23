from __future__ import annotations

from ...model.config.modifier import Modifier

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
# BTN_LEFT/RIGHT/MIDDLE and the extra buttons (side, extra, forward, back); scroll is never held.
BUTTONS = frozenset({0x110, 0x111, 0x112, 0x113, 0x114, 0x115, 0x116})


class SeatState:
    """Held modifiers and buttons from libinput's seat-wide count per key code, so a key held on two
    keyboards stays held until both release it."""

    def __init__(self) -> None:
        self._keys: set[int] = set()
        self._buttons: set[int] = set()

    @property
    def modifiers(self) -> Modifier:
        result = Modifier.NONE
        for code in self._keys:
            result |= MODIFIER_KEYS[code]
        return result

    @property
    def buttons_held(self) -> bool:
        return bool(self._buttons)

    def on_key(self, code: int, seat_count: int) -> bool:
        return code in MODIFIER_KEYS and _update(self._keys, code, seat_count)

    def on_button(self, code: int, seat_count: int) -> bool:
        return code in BUTTONS and _update(self._buttons, code, seat_count)

    def clear_keys(self) -> None:
        self._keys.clear()

    def clear_buttons(self) -> None:
        self._buttons.clear()


def _update(held: set[int], code: int, seat_count: int) -> bool:
    was_held = code in held
    if seat_count > 0:
        held.add(code)
    else:
        held.discard(code)
    return was_held != (seat_count > 0)
