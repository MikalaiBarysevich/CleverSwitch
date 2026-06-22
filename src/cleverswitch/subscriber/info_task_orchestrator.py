import logging
import threading

from ..event.info_task_progress_event import InfoTaskProgressEvent
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..subscriber.task.feature.change_host_feature_task import ChangeHostFeatureTask
from ..subscriber.task.feature.cid_reporting_feature_task import CidReportingFeatureTask
from ..subscriber.task.feature.friendly_name_feature_task import FriendlyNameFeatureTask
from ..subscriber.task.feature.name_and_type_feature_task import NameAndTypeFeatureTask
from ..subscriber.task.find_es_cids_flags_task import FindESCidsFlagsTask
from ..subscriber.task.get_device_friendly_name_task import GetDeviceFriendlyNameTask
from ..subscriber.task.get_device_name_task import GetDeviceNameTask
from ..subscriber.task.get_device_type_task import GetDeviceTypeTask
from ..topic.topics import Topics
from .task.constants import Task

log = logging.getLogger(__name__)

RETRY_BASE_DELAY = 0.5
RETRY_MAX_DELAY = 10.0
RETRY_MAX_ATTEMPTS = 5

_TASK_FACTORIES = {
    Task.Feature.Name.CID_REPORTING: CidReportingFeatureTask,
    Task.Feature.Name.CHANGE_HOST: ChangeHostFeatureTask,
    Task.Feature.Name.NAME_AND_TYPE: NameAndTypeFeatureTask,
    Task.Feature.Name.FRIENDLY_NAME: FriendlyNameFeatureTask,
    Task.Name.FIND_ES_CIDS_FLAGS: FindESCidsFlagsTask,
    Task.Name.GET_DEVICE_TYPE: GetDeviceTypeTask,
    Task.Name.GET_DEVICE_NAME: GetDeviceNameTask,
    Task.Name.GET_DEVICE_FRIENDLY_NAME: GetDeviceFriendlyNameTask,
}


class InfoTaskOrchestrator(Subscriber):
    def __init__(self, device_registry: LogiDeviceRegistry, topics: Topics) -> None:
        self._device_registry = device_registry
        self._topics = topics
        self._announced: set[int] = set()  # wpids already logged as fully discovered
        self._retry_attempts: dict[tuple[int, str], int] = {}
        topics.info_progress.subscribe(self)

    def notify(self, event) -> None:
        if isinstance(event, InfoTaskProgressEvent):
            self._handle_progress(event)

    def _handle_progress(self, event: InfoTaskProgressEvent) -> None:
        device = event.device
        if event.success:
            self._retry_attempts.pop((device.slot, event.step_name), None)
            if not device.pending_steps and device.wpid not in self._announced:
                self._announced.add(device.wpid)
                if device.friendly_name is None and device.name is not None:
                    device.friendly_name = device.name
                log.info(f"Device fully discovered: {device}")
        else:
            if device.connected:
                self._schedule_retry(device, event.step_name)

    def _schedule_retry(self, device, step_name: str) -> None:
        key = (device.slot, step_name)
        attempt = self._retry_attempts.get(key, 0)
        if attempt >= RETRY_MAX_ATTEMPTS:
            log.warning(
                f"Giving up on step={step_name} for wpid=0x{device.wpid:04X} "
                f"slot={device.slot} after {RETRY_MAX_ATTEMPTS} attempts"
            )
            return
        self._retry_attempts[key] = attempt + 1
        delay = min(RETRY_BASE_DELAY * (2**attempt), RETRY_MAX_DELAY)
        log.debug(
            f"Retrying step={step_name} slot={device.slot} attempt={attempt + 1}/{RETRY_MAX_ATTEMPTS} in {delay}s"
        )
        timer = threading.Timer(delay, self._fire_retry, args=(device, step_name))
        timer.daemon = True
        timer.start()

    def _fire_retry(self, device, step_name: str) -> None:
        if not device.connected:
            return
        _TASK_FACTORIES[step_name](device, self._topics).start()
