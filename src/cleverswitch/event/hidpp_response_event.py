import dataclasses

from ..event.event import Event


@dataclasses.dataclass
class HidppResponseEvent(Event):
    feature_index: int
    function: int
    payload: bytes
