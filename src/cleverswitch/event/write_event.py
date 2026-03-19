import dataclasses

from ..event.event import Event

@dataclasses.dataclass
class WriteEvent(Event):
    hid_message: bytes