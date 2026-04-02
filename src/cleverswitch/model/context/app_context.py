import dataclasses
import threading

from ...registry.logi_device_registry import LogiDeviceRegistry
from ...topic.topic import Topic
from ..config.config import Config


@dataclasses.dataclass(frozen=True)
class AppContext:
    device_registry: LogiDeviceRegistry
    topics: dict[str, Topic]
    config: Config
    shutdown: threading.Event
