import dataclasses

from ..event.event import Event


@dataclasses.dataclass
class HidppErrorEvent(Event):
    error_code: int
