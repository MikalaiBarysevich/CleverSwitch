import dataclasses

from ..event.event import Event


@dataclasses.dataclass
class ExternalUndivertEvent(Event):
    feature_index: int
    cid: int
