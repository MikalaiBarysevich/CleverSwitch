import logging

from ..event.device_connected_event import DeviceConnectedEvent
from ..event.host_change_event import HostChangeEvent
from ..hook import hooks
from ..model.config.hooks_config import HooksConfig
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..topic.topics import Topics

log = logging.getLogger(__name__)


class EventHookSubscriber(Subscriber):
    def __init__(self, hooks_config: HooksConfig, device_registry: LogiDeviceRegistry, topics: Topics):
        self._hooks_config = hooks_config
        self._device_registry = device_registry
        self._last_state: dict[int, bool] = {}
        topics.hid_event.subscribe(self)

    def notify(self, event) -> None:
        if isinstance(event, HostChangeEvent):
            self._on_host_change(event)
        elif isinstance(event, DeviceConnectedEvent):
            self._on_device_connected(event)

    def _on_device_connected(self, event: DeviceConnectedEvent) -> None:
        # wpid uniquely identifies a device across receivers — no pid check needed
        device = self._device_registry.get_by_wpid(event.wpid)
        if device is None or device.name is None or device.role is None:
            return
        if self._last_state.get(event.wpid) == event.link_established:
            return
        self._last_state[event.wpid] = event.link_established
        if event.link_established:
            hooks.fire_connect(self._hooks_config, device.name, device.role)
        else:
            hooks.fire_disconnect(self._hooks_config, device.name, device.role)

    def _on_host_change(self, event: HostChangeEvent) -> None:
        device = next(
            (d for d in self._device_registry.all_entries() if d.pid == event.pid and d.slot == event.slot),
            None,
        )
        if device is None or device.name is None or device.role is None:
            return
        hooks.fire_switch(self._hooks_config, device.name, device.role, event.target_host)
