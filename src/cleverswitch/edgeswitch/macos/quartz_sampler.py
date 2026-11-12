from __future__ import annotations

import time
from collections.abc import Callable

from ...model.config.modifier import Modifier
from ..bounds_cache import BoundsCache
from ..geometry import Rect, union
from ..sample import PointerSample
from .quartz import Quartz

# CGEventFlags device-independent masks; each covers the left and right key.
MODIFIER_FLAGS = {
    0x00040000: Modifier.CTRL,  # kCGEventFlagMaskControl
    0x00020000: Modifier.SHIFT,  # kCGEventFlagMaskShift
    0x00080000: Modifier.ALT,  # kCGEventFlagMaskAlternate
    0x00100000: Modifier.META,  # kCGEventFlagMaskCommand
}
MOUSE_BUTTONS = range(5)  # left, right, center, and two extra buttons


class QuartzSampler:
    def __init__(self, quartz_factory: Callable[[], Quartz] = Quartz, clock: Callable[[], float] = time.monotonic):
        self._quartz = quartz_factory()
        self._bounds = BoundsCache(self._read_bounds, clock)

    def sample(self) -> PointerSample | None:
        pos = self._quartz.cursor_pos()
        bounds = self._bounds.get()
        if pos is None or bounds is None:
            return None
        flags = self._quartz.flags()
        modifiers = Modifier.NONE
        for mask, modifier in MODIFIER_FLAGS.items():
            if flags & mask:
                modifiers |= modifier
        buttons_held = any(self._quartz.button_down(b) for b in MOUSE_BUTTONS)
        return PointerSample(x=pos[0], y=pos[1], modifiers=modifiers, buttons_held=buttons_held, bounds=bounds)

    def close(self) -> None:
        pass

    def _read_bounds(self) -> Rect | None:
        return union(Rect(x, y, x + w, y + h) for x, y, w, h in self._quartz.display_bounds() if w > 0 and h > 0)
