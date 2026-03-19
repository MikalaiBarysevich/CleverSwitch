import dataclasses

from ..event.event import Event


@dataclasses.dataclass
class HidppNotificationEvent(Event):
    feature_index: int
    function: int
    payload: bytes
