import dataclasses

from ..event.event import Event


@dataclasses.dataclass
class HidNodeAddedEvent(Event):
    pass
