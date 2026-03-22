from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.device_connected_subscriber import DeviceConnectionSubscriber
from ..subscriber.device_info_subscriber import DeviceInfoSubscriber
from ..subscriber.divert_subscriber import DivertSubscriber
from ..subscriber.diverted_host_change_subscriber import DivertedHostChangeSubscriber
from ..subscriber.external_undivert_subscriber import ExternalUndivertSubscriber
from ..subscriber.host_change_subscriber import HostChangeSubscriber
from ..topic.topic import Topic


def init_subscribers(topics: dict[str, Topic], device_registry: LogiDeviceRegistry) -> None:
    DeviceConnectionSubscriber(device_registry, topics)
    DeviceInfoSubscriber(device_registry, topics)
    DivertSubscriber(device_registry, topics)
    ExternalUndivertSubscriber(device_registry, topics)
    HostChangeSubscriber(device_registry, topics)
    DivertedHostChangeSubscriber(device_registry, topics)
