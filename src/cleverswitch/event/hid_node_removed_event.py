import dataclasses

from ..event.event import Event


@dataclasses.dataclass
class HidNodeRemovedEvent(Event):
    pass
