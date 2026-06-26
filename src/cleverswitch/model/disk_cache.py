import dataclasses

from ..model.logi_device import LogiDevice


@dataclasses.dataclass
class DiskCache:
    version: int
    devices: list[LogiDevice]
