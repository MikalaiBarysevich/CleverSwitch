import dataclasses

from ..event.event import Event
from ..model.config.edge import Edge


@dataclasses.dataclass
class EdgeTouchedEvent(Event):
    edge: Edge
