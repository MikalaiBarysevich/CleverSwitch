import logging

from ..event.device_connected_event import DeviceConnectedEvent
from ..event.divert_event import DivertEvent
from ..hidpp.constants import FEATURE_REPROG_CONTROLS_V4
from ..subscriber.subscriber import Subscriber
from ..event.device_info_request_event import DeviceInfoRequestEvent
from ..model.logi_device import LogiDevice
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..topic.topic import Topic

log = logging.getLogger(__name__)

ALL_INFO_STEPS = {"resolve_reprog", "resolve_change_host", "resolve_x0005", "find_divertable_cids", "get_device_type", "get_device_name"}

class DeviceConnectionSubscriber(Subscriber):

    def __init__(self, device_registry: LogiDeviceRegistry, topics: dict[str, Topic]) -> None:
        self._device_registry = device_registry
        self._topics = topics
        topics["event_topic"].subscribe(self)

    def notify(self, event) -> None:
        if not isinstance(event, DeviceConnectedEvent):
            return

        logi_device = self._device_registry.get_by_wpid(event.wpid)

        if logi_device is not None:
            self._reconnection(event, logi_device)
        else:
            self._new_connection(event)

    def _reconnection(self, event: DeviceConnectedEvent, logi_device: LogiDevice) -> None:
        name = f"'{logi_device.name}'" if logi_device.name is not None else "Device"
        transport = "transport=BT" if logi_device.slot == 0xFF else f"transport=receiver, slot={event.slot}"
        connection = "reconnected" if event.link_established else "disconnected"
        message = f"{name} {connection}: {transport}, wpid=0x{event.wpid:04X}"

        log.info(message)

        if not event.link_established:
            return

        if len(logi_device.divertable_cids) > 0 and FEATURE_REPROG_CONTROLS_V4 in logi_device.available_features:
            self._topics["divert_topic"].publish(DivertEvent(
                slot=event.slot,
                pid=logi_device.pid,
                wpid=logi_device.wpid,
                cids=logi_device.divertable_cids,
            ))

        missing = ALL_INFO_STEPS - logi_device.completed_steps

        if missing:
            log.debug(f"Device reconnected with incomplete setup (missing={missing}): wpid=0x{event.wpid:04X}")
            self._topics["device_info_topic"].publish(DeviceInfoRequestEvent(
                slot=event.slot,
                pid=event.pid,
                wpid=event.wpid,
                type=logi_device.role is None,
                name=logi_device.name is None,
            ))

    def _new_connection(self, event: DeviceConnectedEvent) -> None:
        role = None
        if event.device_type is not None:
            role = "keyboard" if event.device_type == 1 else "mouse"

        device = LogiDevice(
            wpid=event.wpid,
            pid=event.pid,
            slot=event.slot,
            role=role,
            available_features={},
        )

        self._device_registry.register(event.wpid, device)

        self._topics["device_info_topic"].publish(DeviceInfoRequestEvent(
            slot=event.slot,
            pid=event.pid,
            wpid=event.wpid,
            type=event.device_type is None,
        ))