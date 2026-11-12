from __future__ import annotations

import time
from collections.abc import Callable

from ...model.config.modifier import Modifier
from ..bounds_cache import BoundsCache
from ..geometry import Rect
from ..sample import PointerSample
from .user32 import User32

# VK_CONTROL, VK_SHIFT and VK_MENU already cover the left and right keys.
MODIFIER_KEYS = {
    0x11: Modifier.CTRL,
    0x10: Modifier.SHIFT,
    0x12: Modifier.ALT,
    0x5B: Modifier.META,  # VK_LWIN
    0x5C: Modifier.META,  # VK_RWIN
}
BUTTON_KEYS = (0x01, 0x02, 0x04, 0x05, 0x06)  # left, right, middle, X1, X2


class User32Sampler:
    def __init__(self, user32_factory: Callable[[], User32] = User32, clock: Callable[[], float] = time.monotonic):
        self._user32 = user32_factory()
        self._user32.use_per_monitor_dpi()
        self._bounds = BoundsCache(self._read_bounds, clock)

    def sample(self) -> PointerSample | None:
        pos = self._user32.cursor_pos()
        bounds = self._bounds.get()
        if pos is None or bounds is None:
            return None
        modifiers = Modifier.NONE
        for vk, modifier in MODIFIER_KEYS.items():
            if self._user32.key_down(vk):
                modifiers |= modifier
        buttons_held = any(self._user32.key_down(vk) for vk in BUTTON_KEYS)
        return PointerSample(x=pos[0], y=pos[1], modifiers=modifiers, buttons_held=buttons_held, bounds=bounds)

    def close(self) -> None:
        pass

    def _read_bounds(self) -> Rect | None:
        x, y, width, height = self._user32.virtual_screen()
        if width <= 0 or height <= 0:
            return None
        return Rect(x, y, x + width, y + height)
