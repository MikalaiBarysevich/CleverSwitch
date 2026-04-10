import dataclasses

from ..event.event import Event


@dataclasses.dataclass
class ExternalUnsetFlagEvent(Event):
    feature_index: int
    cid: int
