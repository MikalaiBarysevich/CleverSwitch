from __future__ import annotations

import time
from collections.abc import Callable

from ...model.config.modifier import Modifier
from ..bounds_cache import BoundsCache
from ..geometry import Rect
from ..sample import PointerSample
from .xcb import Xcb

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


class XcbSampler:
    def __init__(self, xcb_factory: Callable[[], Xcb] = Xcb, clock: Callable[[], float] = time.monotonic):
        self._xcb = xcb_factory()
        mapping = self._xcb.keyboard_mapping()
        self._keycodes = modifier_keycodes(*mapping) if mapping is not None else {}
        self._bounds = BoundsCache(self._read_bounds, clock)

    def sample(self) -> PointerSample | None:
        if self._xcb.has_error():
            raise OSError("the X server connection was lost")
        pointer = self._xcb.query_pointer()
        keymap = self._xcb.query_keymap()
        bounds = self._bounds.get()
        if pointer is None or keymap is None or bounds is None:
            return None
        x, y, mask = pointer
        return PointerSample(
            x=x,
            y=y,
            modifiers=modifiers_from_keymap(keymap, self._keycodes),
            buttons_held=bool(mask & BUTTON_MASK),
            bounds=bounds,
        )

    def close(self) -> None:
        self._xcb.close()

    # Under RandR or Xinerama the root window already spans every monitor.
    def _read_bounds(self) -> Rect | None:
        geometry = self._xcb.root_geometry()
        if geometry is None:
            return None
        x, y, width, height = geometry
        if width <= 0 or height <= 0:
            return None
        return Rect(x, y, x + width, y + height)
