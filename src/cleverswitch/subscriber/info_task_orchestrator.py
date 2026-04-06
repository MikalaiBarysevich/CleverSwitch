import logging

from ..event.info_task_progress_event import InfoTaskProgressEvent
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..subscriber.task.feature.change_host_feature_task import ChangeHostFeatureTask
from ..subscriber.task.feature.name_and_type_feature_task import NameAndTypeFeatureTask
from ..subscriber.task.feature.reprog_feature_task import ReprogFeatureTask
from ..subscriber.task.find_divertable_cids_task import FindDivertableCidsTask
from ..subscriber.task.get_device_name_task import GetDeviceNameTask
from ..subscriber.task.get_device_type_task import GetDeviceTypeTask
from ..topic.topics import Topics

log = logging.getLogger(__name__)

_TASK_FACTORIES = {
    "resolve_reprog": ReprogFeatureTask,
    "resolve_change_host": ChangeHostFeatureTask,
    "resolve_x0005": NameAndTypeFeatureTask,
    "find_divertable_cids": FindDivertableCidsTask,
    "get_device_type": GetDeviceTypeTask,
    "get_device_name": GetDeviceNameTask,
}


class InfoTaskOrchestrator(Subscriber):
    def __init__(self, device_registry: LogiDeviceRegistry, topics: Topics) -> None:
        self._device_registry = device_registry
        self._topics = topics
        self._announced: set[int] = set()  # wpids already logged as fully discovered
        topics.info_progress.subscribe(self)

    def notify(self, event) -> None:
        if isinstance(event, InfoTaskProgressEvent):
            self._handle_progress(event)

    def _handle_progress(self, event: InfoTaskProgressEvent) -> None:
        device = event.device
        if event.success:
            if not device.pending_steps and device.wpid not in self._announced:
                self._announced.add(device.wpid)
                log.info("Device fully discovered: slot=%d wpid=0x%04X %s", device.slot, device.wpid, device)
        else:
            if device.connected:
                log.debug("Retrying step=%s slot=%d", event.step_name, device.slot)
                _TASK_FACTORIES[event.step_name](device, self._topics).start()
