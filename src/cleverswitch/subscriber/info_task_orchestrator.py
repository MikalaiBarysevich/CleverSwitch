import logging
import threading

from ..cache.device_cache import DeviceCache
from ..event.device_info_request_event import DeviceInfoRequestEvent
from ..event.info_task_progress_event import InfoTaskProgressEvent
from ..model.logi_device import LogiDevice
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

MAX_DISCOVERY_ATTEMPTS = 5

_CAPPED_STEPS = frozenset(
    {
        Task.Feature.Name.CHANGE_HOST,
        Task.Feature.Name.CID_REPORTING,
        Task.Name.FIND_ES_CIDS_FLAGS,
    }
)


class InfoTaskOrchestrator(Subscriber):
    def __init__(self, device_registry: LogiDeviceRegistry, topics: Topics, cache: DeviceCache) -> None:
        self._device_registry = device_registry
        self._topics = topics
        self._cache = cache
        self._announced: set[int] = set()  # wpids already logged as fully discovered
        self._attempts: dict[tuple[int, str], int] = {}
        self._lock = threading.Lock()
        topics.info_progress.subscribe(self)
        topics.device_info.subscribe(self)

    def notify(self, event) -> None:
        if isinstance(event, InfoTaskProgressEvent):
            self._handle_progress(event)
        elif isinstance(event, DeviceInfoRequestEvent):
            self._reset_budget(event.wpid)

    def _handle_progress(self, event: InfoTaskProgressEvent) -> None:
        device = event.device
        if event.success:
            if not device.pending_steps and device.wpid not in self._announced:
                self._announced.add(device.wpid)
                self._cache.save(device)
                if device.friendly_name is None and device.name is not None:
                    device.friendly_name = device.name
                log.info(f"Device fully discovered: {device}")
        else:
            if device.connected and self._consume_attempt(device, event.step_name):
                log.debug(f"Retrying step={event.step_name} slot={device.slot}")
                _TASK_FACTORIES[event.step_name](device, self._topics).start()

    def _consume_attempt(self, device: LogiDevice, step_name: str) -> bool:
        if step_name not in _CAPPED_STEPS:
            return True

        with self._lock:
            attempts = self._attempts.get((device.wpid, step_name), 0) + 1
            self._attempts[(device.wpid, step_name)] = attempts

        if attempts < MAX_DISCOVERY_ATTEMPTS:
            return True

        if attempts == MAX_DISCOVERY_ATTEMPTS:
            log.critical(
                f"Giving up on step={step_name} for {device.display_name} wpid=0x{device.wpid:04X} "
                f"after {attempts} attempts. Host switching will not work for this device. "
                f"CleverSwitch keeps running; reconnect the device to retry"
            )
        return False

    def _reset_budget(self, wpid: int) -> None:
        with self._lock:
            for key in [key for key in self._attempts if key[0] == wpid]:
                del self._attempts[key]
