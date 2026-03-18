import dataclasses

from ..event.event import Event


@dataclasses.dataclass
class DivertEvent(Event):
    wpid: int
    cids: set[int]
    divert: bool = True
