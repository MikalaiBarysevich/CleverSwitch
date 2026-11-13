from __future__ import annotations

import dataclasses
from collections.abc import Iterable

from ..model.config.edge import Edge

EDGE_TOLERANCE_PX = 1.0


# Top-left origin, y grows down; right and bottom are exclusive.
@dataclasses.dataclass(frozen=True)
class Rect:
    left: float
    top: float
    right: float
    bottom: float


def union(rects: Iterable[Rect]) -> Rect | None:
    rects = list(rects)
    if not rects:
        return None
    return Rect(
        left=min(r.left for r in rects),
        top=min(r.top for r in rects),
        right=max(r.right for r in rects),
        bottom=max(r.bottom for r in rects),
    )


def edges_at(x: float, y: float, rect: Rect, tolerance: float = EDGE_TOLERANCE_PX) -> frozenset[Edge]:
    edges = set()
    if x <= rect.left + tolerance:
        edges.add(Edge.LEFT)
    if x >= rect.right - 1 - tolerance:
        edges.add(Edge.RIGHT)
    if y <= rect.top + tolerance:
        edges.add(Edge.TOP)
    if y >= rect.bottom - 1 - tolerance:
        edges.add(Edge.BOTTOM)
    return frozenset(edges)
