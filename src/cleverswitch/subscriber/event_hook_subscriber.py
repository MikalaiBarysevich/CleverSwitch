import logging
import threading

from ..cache.device_cache import DeviceCache
from ..event.device_connected_event import DeviceConnectedEvent
from ..event.host_change_event import HostChangeEvent
from ..event.info_task_progress_event import InfoTaskProgressEvent
from ..hook import hooks
from ..model.config.hooks_config import HooksConfig
from ..model.logi_device import LogiDevice
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..topic.topics import Topics

log = logging.getLogger(__name__)


class EventHookSubscriber(Subscriber):
    def __init__(
        self, hooks_config: HooksConfig, device_registry: LogiDeviceRegistry, topics: Topics, cache: DeviceCache
    ):
        self._hooks_config = hooks_config
        self._device_registry = device_registry
        self._cache = cache
        self._last_state: dict[int, bool] = {}
        self._lock = threading.Lock()
        topics.hid_event.subscribe(self)
        topics.info_progress.subscribe(self)

    def notify(self, event) -> None:
        if isinstance(event, HostChangeEvent):
            self._on_host_change(event)
        elif isinstance(event, DeviceConnectedEvent):
            self._on_device_connected(event)
        elif isinstance(event, InfoTaskProgressEvent):
            self._on_info_progress(event)

    def _on_device_connected(self, event: DeviceConnectedEvent) -> None:
        # wpid uniquely identifies a device across receivers — no pid check needed
        device = self._device_registry.get_by_wpid(event.wpid) or self._cache.find_by_wpid(event.wpid)
        if device is None:
            return
        self._fire_on_change(device, event.link_established)

    # A device first seen without a name or role gets them during discovery, after its connect event.
    def _on_info_progress(self, event: InfoTaskProgressEvent) -> None:
        if event.success and event.device.connected:
            self._fire_on_change(event.device, True)

    def _fire_on_change(self, device: LogiDevice, connected: bool) -> None:
        if device.name is None or device.role is None:
            return
        with self._lock:
            if self._last_state.get(device.wpid) == connected:
                return
            self._last_state[device.wpid] = connected
        if connected:
            hooks.fire_connect(self._hooks_config, device.display_name, device.role)
        else:
            hooks.fire_disconnect(self._hooks_config, device.display_name, device.role)

    def _on_host_change(self, event: HostChangeEvent) -> None:
        device = next(
            (d for d in self._device_registry.all_entries() if d.pid == event.pid and d.slot == event.slot),
            None,
        )
        if device is None or device.name is None or device.role is None:
            return
        hooks.fire_switch(self._hooks_config, device.display_name, device.role, event.target_host)
