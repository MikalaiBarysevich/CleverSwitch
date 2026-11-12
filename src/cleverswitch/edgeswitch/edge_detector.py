from __future__ import annotations

import time
from collections.abc import Callable

from ..model.config.edge import EDGE_PRIORITY, Edge
from ..model.config.modifier import Modifier
from .geometry import EDGE_TOLERANCE_PX, Rect, edges_at


class EdgeDetector:
    """Fires when the cursor moves onto a mapped edge while exactly the configured modifiers are held.

    Backends report every modifier/button change through on_state() and, only while `active`, the cursor
    position through on_pointer(). An edge is armed once the cursor has been seen off it during the current
    held period, so pressing the modifier while already at an edge never fires: the keyboard arrives on the
    other host with the modifier still down and that host's cursor may sit at the edge leading back. A held
    mouse button (ctrl-drag, ctrl-click on a scrollbar) blocks it. After firing, the detector stays latched
    until the modifiers stop matching, so a modifier the OS still believes held after a switch cannot fire
    on a later plain edge touch.
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
        self._state: tuple[Modifier, bool] = (Modifier.NONE, False)
        self._armed: set[Edge] = set()
        self._latched = False
        self._cooldown_until = float("-inf")

    def on_state(self, modifiers: Modifier, buttons_held: bool) -> None:
        state = (modifiers, buttons_held)
        if state == self._state:
            return
        self._state = state
        self._armed.clear()
        if modifiers != self._modifiers:
            self._latched = False

    @property
    def active(self) -> bool:
        modifiers, buttons_held = self._state
        return modifiers == self._modifiers and not buttons_held and not self._latched

    def on_pointer(self, x: float, y: float, bounds: Rect | None) -> Edge | None:
        if not self.active or bounds is None:
            return None
        at = edges_at(x, y, bounds, self._tolerance) & self._edges
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
        self._latched = True
        return edge
