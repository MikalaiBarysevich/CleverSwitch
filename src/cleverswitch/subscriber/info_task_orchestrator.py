import logging

from ..event.info_task_progress_event import InfoTaskProgressEvent
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..subscriber.task.feature.change_host_feature_task import ChangeHostFeatureTask
from ..subscriber.task.feature.cid_reporting_feature_task import CidReportingFeatureTask
from ..subscriber.task.feature.name_and_type_feature_task import NameAndTypeFeatureTask
from ..subscriber.task.find_es_cids_flags_task import FindESCidsFlagsTask
from ..subscriber.task.get_device_name_task import GetDeviceNameTask
from ..subscriber.task.get_device_type_task import GetDeviceTypeTask
from ..topic.topics import Topics
from .task.constants import Task

log = logging.getLogger(__name__)

_TASK_FACTORIES = {
    Task.Feature.Name.CID_REPORTING: CidReportingFeatureTask,
    Task.Feature.Name.CHANGE_HOST: ChangeHostFeatureTask,
    Task.Feature.Name.NAME_AND_TYPE: NameAndTypeFeatureTask,
    Task.Name.FIND_ES_CIDS_FLAGS: FindESCidsFlagsTask,
    Task.Name.GET_DEVICE_TYPE: GetDeviceTypeTask,
    Task.Name.GET_DEVICE_NAME: GetDeviceNameTask,
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
                log.info(f"Device fully discovered: {device}")
        else:
            if device.connected:
                log.debug(f"Retrying step={event.step_name} slot={device.slot}")
                _TASK_FACTORIES[event.step_name](device, self._topics).start()
