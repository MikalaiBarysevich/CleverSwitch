import logging
import threading

from ..errors import ResponseTimeoutError
from ..event.device_info_request_event import DeviceInfoRequestEvent
from ..event.hidpp_error_event import HidppErrorEvent
from ..event.hidpp_response_event import HidppResponseEvent
from ..hidpp.constants import (
    FEATURE_CHANGE_HOST,
    FEATURE_DEVICE_TYPE_AND_NAME,
    FEATURE_REPROG_CONTROLS_V4,
    SW_ID_FIND_DIVERTABLE_CIDS,
    SW_ID_GET_DEVICE_NAME,
    SW_ID_GET_DEVICE_TYPE,
    SW_ID_RESOLVE_CHANGE_HOST,
    SW_ID_RESOLVE_DEVICE_TYPE_NAME,
    SW_ID_RESOLVE_REPROG,
)
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..task.find_divertable_cids_task import FindDivertableCidsTask
from ..task.get_device_name_task import GetDeviceNameTask
from ..task.get_device_type_task import GetDeviceTypeTask
from ..task.info_task import InfoTask
from ..task.resolve_feature_task import ResolveFeatureTask
from ..topic.topic import Topic

log = logging.getLogger(__name__)


class DeviceInfoSubscriber(Subscriber):

    def __init__(self, device_registry: LogiDeviceRegistry, topics: dict[str, Topic]) -> None:
        self._device_registry = device_registry
        self._topics = topics
        self._lock = threading.Lock()
        self._active_tasks: dict[int, InfoTask] = {}  # sw_id → task
        topics["event_topic"].subscribe(self)
        topics["device_info_topic"].subscribe(self)

    def notify(self, event) -> None:
        if isinstance(event, DeviceInfoRequestEvent):
            self._handle_setup(event)
        elif isinstance(event, (HidppResponseEvent, HidppErrorEvent)):
            self._forward_event(event)

    def _forward_event(self, event: HidppResponseEvent | HidppErrorEvent) -> None:
        with self._lock:
            task = self._active_tasks.get(event.sw_id)
        if task is not None:
            task.forward_event(event)

    def _handle_setup(self, event: DeviceInfoRequestEvent) -> None:
        device = self._device_registry.get_by_wpid(event.wpid)
        if device is None:
            log.warning("DeviceInfoSubscriber: device wpid=0x%04X not found in registry", event.wpid)
            return

        log.info(
            "Starting device info setup for slot=%d wpid=0x%04X (completed=%s)",
            event.slot, event.wpid, device.completed_steps,
        )

        # Phase 1: Resolve feature indices (parallel — each has unique SW_ID)
        resolve_tasks: list[InfoTask] = []
        if "resolve_reprog" not in device.completed_steps:
            resolve_tasks.append(
                ResolveFeatureTask(SW_ID_RESOLVE_REPROG, "resolve_reprog", device, self._topics, FEATURE_REPROG_CONTROLS_V4)
            )
        if "resolve_change_host" not in device.completed_steps:
            resolve_tasks.append(
                ResolveFeatureTask(SW_ID_RESOLVE_CHANGE_HOST, "resolve_change_host", device, self._topics, FEATURE_CHANGE_HOST)
            )
        if "resolve_x0005" not in device.completed_steps:
            resolve_tasks.append(
                ResolveFeatureTask(SW_ID_RESOLVE_DEVICE_TYPE_NAME, "resolve_x0005", device, self._topics, FEATURE_DEVICE_TYPE_AND_NAME)
            )

        if resolve_tasks:
            self._run_tasks_parallel(resolve_tasks)

        # Mark steps complete for info we don't need to query
        if not event.type:
            device.completed_steps.add("get_device_type")
        if not event.name:
            device.completed_steps.add("get_device_name")

        # Phase 2: Tasks that depend on resolved features (parallel where possible)
        phase2_tasks: list[InfoTask] = []
        if "find_divertable_cids" not in device.completed_steps:
            phase2_tasks.append(FindDivertableCidsTask(SW_ID_FIND_DIVERTABLE_CIDS, device, self._topics))
        if "get_device_type" not in device.completed_steps:
            phase2_tasks.append(GetDeviceTypeTask(SW_ID_GET_DEVICE_TYPE, device, self._topics))
        if "get_device_name" not in device.completed_steps:
            phase2_tasks.append(GetDeviceNameTask(SW_ID_GET_DEVICE_NAME, device, self._topics))

        if phase2_tasks:
            self._run_tasks_parallel(phase2_tasks)

        log.info(
            "Device info setup complete for slot=%d: name=%s, role=%s, features=%s, divertable_cids=%s",
            event.slot, device.name, device.role, device.available_features, device.divertable_cids,
        )

    def _run_tasks_parallel(self, tasks: list[InfoTask]) -> None:
        # Register all tasks so forwarded events reach them
        with self._lock:
            for task in tasks:
                self._active_tasks[task._sw_id] = task

        threads: list[threading.Thread] = []
        errors: list[ResponseTimeoutError] = []

        def _run_task(task: InfoTask) -> None:
            try:
                task.run()
            except ResponseTimeoutError as e:
                errors.append(e)

        for task in tasks:
            t = threading.Thread(target=_run_task, args=(task,), daemon=True)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Unregister tasks
        with self._lock:
            for task in tasks:
                self._active_tasks.pop(task._sw_id, None)

        if errors:
            log.warning("Device info task(s) timed out: %s", [str(e) for e in errors])
