import logging

from ..event.device_info_request_event import DeviceInfoRequestEvent
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..topic.topics import Topics
from .task.feature.change_host_feature_task import ChangeHostFeatureTask
from .task.feature.cid_reporting_feature_task import CidReportingFeatureTask
from .task.feature.name_and_type_feature_task import NameAndTypeFeatureTask

log = logging.getLogger(__name__)


class DeviceInfoSubscriber(Subscriber):
    def __init__(self, device_registry: LogiDeviceRegistry, topics: Topics) -> None:
        self._device_registry = device_registry
        self._topics = topics
        topics.device_info.subscribe(self)

    def notify(self, event) -> None:
        if isinstance(event, DeviceInfoRequestEvent):
            self._handle_setup(event)

    def _handle_setup(self, event: DeviceInfoRequestEvent) -> None:
        device = self._device_registry.get_by_wpid(event.wpid)
        if device is None:
            log.warning("Device wpid=0x%04X not found in registry", event.wpid)
            return

        log.info(f"Found new device with wpid={hex(event.wpid)} on slot={event.slot}. Configuring...")

        # Skip-marks for info we don't need to query
        if not event.type:
            device.pending_steps.discard("get_device_type")
        if not event.name:
            device.pending_steps.discard("get_device_name")
        if device.role is not None and device.role != "keyboard":
            device.pending_steps.discard("resolve_reprog")
            device.pending_steps.discard("find_es_cids_flags")

        if device.role == "keyboard":
            CidReportingFeatureTask(device, self._topics).start()
        ChangeHostFeatureTask(device, self._topics).start()
        NameAndTypeFeatureTask(device, self._topics).start()
