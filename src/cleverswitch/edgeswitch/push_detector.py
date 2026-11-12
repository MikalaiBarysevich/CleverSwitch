from __future__ import annotations

import time
from collections.abc import Callable

from ..model.config.edge import EDGE_PRIORITY, Edge
from ..model.config.modifier import Modifier


class PushDetector:
    """Edge detection from relative motion, for evdev where the cursor position is unknown.

    While exactly the configured modifiers are held (and no mouse button), motion is summed per axis;
    a sum past the threshold counts as touching that edge. Reversing direction restarts the axis, so
    wiggling does not add up. After firing it stays latched until the modifiers stop matching.
    """

    def __init__(
        self,
        edges: frozenset[Edge],
        modifiers: Modifier,
        cooldown_s: float,
        threshold: int,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._edges = edges
        self._modifiers = modifiers
        self._cooldown_s = cooldown_s
        self._threshold = threshold
        self._clock = clock
        self._state: tuple[Modifier, bool] = (Modifier.NONE, False)
        self._active = False
        self._latched = False
        self._ax = 0
        self._ay = 0
        self._cooldown_until = float("-inf")

    def on_state(self, modifiers: Modifier, buttons_held: bool) -> None:
        state = (modifiers, buttons_held)
        if state == self._state:
            return
        self._state = state
        self._ax = self._ay = 0
        self._active = modifiers == self._modifiers and not buttons_held
        if modifiers != self._modifiers:
            self._latched = False

    def on_motion(self, dx: int, dy: int) -> Edge | None:
        if not self._active or self._latched:
            return None
        self._ax = _accumulate(self._ax, dx)
        self._ay = _accumulate(self._ay, dy)

        crossed = {
            Edge.LEFT: self._ax <= -self._threshold,
            Edge.RIGHT: self._ax >= self._threshold,
            Edge.TOP: self._ay <= -self._threshold,
            Edge.BOTTOM: self._ay >= self._threshold,
        }
        edge = next((e for e in EDGE_PRIORITY if crossed[e] and e in self._edges), None)
        if edge is None:
            return None

        self._ax = self._ay = 0
        now = self._clock()
        if now < self._cooldown_until:
            return None
        self._latched = True
        self._cooldown_until = now + self._cooldown_s
        return edge


def _accumulate(total: int, delta: int) -> int:
    if delta and total and (delta > 0) != (total > 0):
        return delta
    return total + delta
