import dataclasses

from ..event.event import Event


@dataclasses.dataclass
class HostChangeEvent(Event):
    target_host: int
