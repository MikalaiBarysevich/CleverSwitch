import dataclasses

from ..event.event import Event

@dataclasses.dataclass
class DeviceConnectedEvent(Event):
    slot: int
