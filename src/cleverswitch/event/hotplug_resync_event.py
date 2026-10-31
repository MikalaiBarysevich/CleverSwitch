import dataclasses

from ..event.event import Event


@dataclasses.dataclass
class HotplugResyncEvent(Event):
    pass
