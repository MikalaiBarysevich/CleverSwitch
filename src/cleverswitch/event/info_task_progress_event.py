import dataclasses

from ..model.logi_device import LogiDevice
from .event import Event


@dataclasses.dataclass
class InfoTaskProgressEvent(Event):
    step_name: str
    success: bool
    device: LogiDevice
