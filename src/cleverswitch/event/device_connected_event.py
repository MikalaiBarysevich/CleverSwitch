import dataclasses

from ..event.event import Event


@dataclasses.dataclass
class DeviceConnectedEvent(Event):
    slot: int
    link_established: bool
    wpid: int
    device_type: int | None = None
