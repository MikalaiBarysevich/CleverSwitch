import logging

from .task.feature.change_host_feature_task import ChangeHostFeatureTask
from .task.feature.name_and_type_feature_task import NameAndTypeFeatureTask
from .task.feature.reprog_feature_task import ReprogFeatureTask
from ..event.device_info_request_event import DeviceInfoRequestEvent
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..topic.topic import Topic

log = logging.getLogger(__name__)


class DeviceInfoSubscriber(Subscriber):
    def __init__(self, device_registry: LogiDeviceRegistry, topics: dict[str, Topic]) -> None:
        self._device_registry = device_registry
        self._topics = topics
        topics["device_info_topic"].subscribe(self)

    def notify(self, event) -> None:
        if isinstance(event, DeviceInfoRequestEvent):
            self._handle_setup(event)

    def _handle_setup(self, event: DeviceInfoRequestEvent) -> None:
        device = self._device_registry.get_by_wpid(event.wpid)
        if device is None:
            log.warning("DeviceInfoSubscriber: device wpid=0x%04X not found in registry", event.wpid)
            return

        log.info(
            "Starting device info setup for slot=%d wpid=0x%04X (pending=%s)",
            event.slot,
            event.wpid,
            device.pending_steps,
        )

        # Skip-marks for info we don't need to query
        if not event.type:
            device.pending_steps.discard("get_device_type")
        if not event.name:
            device.pending_steps.discard("get_device_name")

        ReprogFeatureTask(device, self._topics).start()
        ChangeHostFeatureTask(device, self._topics).start()
        NameAndTypeFeatureTask(device, self._topics).start()
