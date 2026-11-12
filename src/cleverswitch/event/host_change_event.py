import dataclasses
from enum import StrEnum

from ..event.event import Event


class SwitchSource(StrEnum):
    DEVICE = "device"
    EDGE = "edge"


@dataclasses.dataclass
class HostChangeEvent(Event):
    target_host: int
    source: SwitchSource = SwitchSource.DEVICE
