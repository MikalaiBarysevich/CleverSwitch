import dataclasses

from ..event.event import Event


@dataclasses.dataclass
class DeviceInfoRequestEvent(Event):
    wpid: int
    type: bool
    name: bool = True
