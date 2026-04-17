import dataclasses

from ..event.event import Event


@dataclasses.dataclass
class HidppErrorEvent(Event):
    sw_id: int
    error_code: int
