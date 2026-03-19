import dataclasses

from ..event.event import Event


@dataclasses.dataclass
class DivertedHostChangeEvent(Event):
    target_host: int
