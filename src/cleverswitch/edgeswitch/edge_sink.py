from __future__ import annotations

from collections.abc import Callable

from ..model.config.edge import Edge
from ..model.config.modifier import Modifier
from .edge_detector import EdgeDetector
from .geometry import Rect

Location = tuple[float, float, Rect | None]


class EdgeSink:
    """Where a backend's input events meet the detector. The cursor position (an OS call) is looked up only
    for a motion event while the gesture is held, and nothing is published once the backend is stopping.

    A compositor that reports edge changes instead of positions (KWin, GNOME Shell) goes through on_edges().
    The last set is fed again after every state change, so pressing the modifier off an edge arms it and
    pressing it on an edge does not, exactly as a position lookup would.
    """

    def __init__(self, detector: EdgeDetector, publish: Callable[[Edge], None], stopping: Callable[[], bool]):
        self._detector = detector
        self._publish = publish
        self._stopping = stopping
        self._edges: frozenset[Edge] | None = None

    def on_state(self, modifiers: Modifier, buttons_held: bool) -> None:
        self._detector.on_state(modifiers, buttons_held)
        if self._edges is not None:
            self._feed(self._edges)

    def on_edges(self, edges: frozenset[Edge]) -> None:
        self._edges = edges
        self._feed(edges)

    def _feed(self, edges: frozenset[Edge]) -> None:
        if self._stopping():
            return
        edge = self._detector.on_edges(edges)
        if edge is not None and not self._stopping():
            self._publish(edge)

    def on_motion(self, locate: Callable[[], Location | None]) -> None:
        if not self._detector.active or self._stopping():
            return
        location = locate()
        if location is None:
            return
        edge = self._detector.on_pointer(*location)
        if edge is not None and not self._stopping():
            self._publish(edge)
