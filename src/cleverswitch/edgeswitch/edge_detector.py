from __future__ import annotations

import time
from collections.abc import Callable

from ..model.config.edge import EDGE_PRIORITY, Edge
from ..model.config.modifier import Modifier
from .geometry import EDGE_TOLERANCE_PX, edges_at
from .sample import PointerSample


class EdgeDetector:
    """Fires when the cursor moves onto a mapped edge while exactly the configured modifiers are held.

    An edge is armed once the cursor has been seen off it during the current held period, so pressing
    the modifier while already at an edge never fires. That is what stops a switch from bouncing back:
    the keyboard arrives on the other host with the modifier still down and that host's cursor may sit
    at the edge leading back. A held mouse button (ctrl-drag, ctrl-click on a scrollbar) blocks it.
    """

    def __init__(
        self,
        edges: frozenset[Edge],
        modifiers: Modifier,
        cooldown_s: float,
        clock: Callable[[], float] = time.monotonic,
        tolerance: float = EDGE_TOLERANCE_PX,
    ):
        self._edges = edges
        self._modifiers = modifiers
        self._cooldown_s = cooldown_s
        self._clock = clock
        self._tolerance = tolerance
        self._armed: set[Edge] = set()
        self._cooldown_until = float("-inf")

    def feed(self, sample: PointerSample | None) -> Edge | None:
        if sample is None:
            return None
        if sample.modifiers != self._modifiers or sample.buttons_held:
            self._armed.clear()
            return None

        at = edges_at(sample.x, sample.y, sample.bounds, self._tolerance) & self._edges
        self._armed |= self._edges - at
        edge = next((e for e in EDGE_PRIORITY if e in at and e in self._armed), None)
        if edge is None:
            return None

        # A touch inside the cooldown must leave the edge and come back, or it would fire on expiry.
        self._armed -= at
        now = self._clock()
        if now < self._cooldown_until:
            return None
        self._cooldown_until = now + self._cooldown_s
        return edge
