import dataclasses

from .topic import Topic


@dataclasses.dataclass
class Topics:
    hid_event: Topic
    write: Topic
    device_info: Topic
    flags: Topic
    info_progress: Topic
