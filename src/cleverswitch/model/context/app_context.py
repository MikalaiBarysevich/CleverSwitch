import dataclasses
import threading

from ...registry.logi_device_registry import LogiDeviceRegistry
from ...topic.topics import Topics
from ..config.config import Config


@dataclasses.dataclass(frozen=True)
class AppContext:
    device_registry: LogiDeviceRegistry
    topics: Topics
    config: Config
    shutdown: threading.Event
