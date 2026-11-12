from __future__ import annotations

import time
from collections.abc import Callable

from .geometry import Rect

BOUNDS_TTL_S = 1.0


class BoundsCache:
    """Re-reads the desktop bounds at most once per TTL, so a monitor plugged in mid-session is picked up
    without querying the display layout on every poll."""

    def __init__(
        self, read: Callable[[], Rect | None], clock: Callable[[], float] = time.monotonic, ttl_s: float = BOUNDS_TTL_S
    ):
        self._read = read
        self._clock = clock
        self._ttl_s = ttl_s
        self._bounds: Rect | None = None
        self._read_at = float("-inf")

    def get(self) -> Rect | None:
        now = self._clock()
        if self._bounds is None or now - self._read_at >= self._ttl_s:
            self._bounds = self._read()
            self._read_at = now
        return self._bounds
