from __future__ import annotations

import dataclasses
from typing import Protocol

from ..model.config.modifier import Modifier
from .geometry import Rect


@dataclasses.dataclass(frozen=True)
class PointerSample:
    x: float
    y: float
    modifiers: Modifier  # left and right keys already merged
    buttons_held: bool
    bounds: Rect  # desktop bounding box at sample time


class PointerSampler(Protocol):
    def sample(self) -> PointerSample | None: ...

    def close(self) -> None: ...
