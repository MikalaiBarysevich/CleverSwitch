from __future__ import annotations

import logging
import time
from collections.abc import Callable

from ..model.config.edge import EDGE_PRIORITY, Edge
from ..model.config.modifier import Modifier
from .geometry import EDGE_TOLERANCE_PX, Rect, edges_at

log = logging.getLogger(__name__)


def describe_modifiers(modifiers: Modifier) -> str:
    names = [m.name.lower() for m in Modifier if m in modifiers]
    return "+".join(names) if names else "none"


class EdgeDetector:
    """Fires when the cursor moves onto a mapped edge while exactly the configured modifiers are held.

    Backends report every modifier/button change through on_state() and, only while `active`, the cursor
    position through on_pointer(), or the outer edges under the cursor through on_edges() when only the
    compositor knows the position. An edge is armed once the cursor has been seen off it during the current
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
        self._note: tuple | None = None

    # Debug tracing says why nothing happened; it logs on a change only, so a burst of motion stays quiet.
    def _trace(self, note: tuple, message: str) -> None:
        if note != self._note:
            self._note = note
            log.debug(message)

    def on_state(self, modifiers: Modifier, buttons_held: bool) -> None:
        state = (modifiers, buttons_held)
        if state == self._state:
            return
        self._state = state
        self._armed.clear()
        self._note = None
        if modifiers != self._modifiers:
            self._latched = False
        log.debug(
            f"Edge switch state: modifiers={describe_modifiers(modifiers)} "
            f"(configured: {describe_modifiers(self._modifiers)}, "
            f"match: {modifiers == self._modifiers}), button held: {buttons_held}, active: {self.active}"
        )

    @property
    def active(self) -> bool:
        modifiers, buttons_held = self._state
        return modifiers == self._modifiers and not buttons_held and not self._latched

    def on_pointer(self, x: float, y: float, bounds: Rect | None) -> Edge | None:
        if not self.active or bounds is None:
            return None
        return self.on_edges(edges_at(x, y, bounds, self._tolerance))

    def on_edges(self, at: frozenset[Edge]) -> Edge | None:
        if not self.active:
            return None
        at = at & self._edges
        self._armed |= self._edges - at
        edge = next((e for e in EDGE_PRIORITY if e in at and e in self._armed), None)
        if edge is None:
            if at:
                self._trace(
                    ("unarmed", at),
                    f"Edge switch ignores {sorted(e.value for e in at)}: it was already under the cursor when "
                    f"the gesture started, so it must be left and touched again",
                )
            return None

        # A touch inside the cooldown must leave the edge and come back, or it would fire on expiry.
        self._armed -= at
        now = self._clock()
        if now < self._cooldown_until:
            self._trace(
                ("cooldown", edge), f"Edge switch ignores '{edge}': cooling down for {self._cooldown_until - now:.2f}s"
            )
            return None
        self._note = None
        self._cooldown_until = now + self._cooldown_s
        self._latched = True
        return edge
