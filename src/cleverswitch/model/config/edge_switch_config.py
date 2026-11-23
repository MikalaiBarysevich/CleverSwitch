import dataclasses

from .edge import Edge
from .modifier import Modifier

DEFAULT_COOLDOWN_MS = 1000


@dataclasses.dataclass(frozen=True)
class EdgeSwitchConfig:
    enabled: bool = False
    modifiers: Modifier = Modifier.CTRL
    cooldown_ms: int = DEFAULT_COOLDOWN_MS
    edges: dict[Edge, int] = dataclasses.field(default_factory=dict)  # edge → 0-based host
