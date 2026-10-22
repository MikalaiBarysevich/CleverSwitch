import dataclasses

from ..event.event import Event


@dataclasses.dataclass
class HidppErrorEvent(Event):
    feature_index: int
    function: int
    sw_id: int
    error_code: int
