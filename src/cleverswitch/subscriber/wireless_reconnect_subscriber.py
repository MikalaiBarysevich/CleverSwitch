import logging

from ..event.device_connected_event import DeviceConnectedEvent
from ..event.hidpp_notification_event import HidppNotificationEvent
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..topic.topics import Topics

log = logging.getLogger(__name__)


class WirelessReconnectSubscriber(Subscriber):
    def __init__(self, device_registry: LogiDeviceRegistry, topics: Topics) -> None:
        self._device_registry = device_registry
        self._topics = topics
        topics.hid_event.subscribe(self)

    def notify(self, event) -> None:
        if not isinstance(event, HidppNotificationEvent) or event.function != 0:
            return

        device = next(
            (d for d in self._device_registry.all_entries() if d.pid == event.pid and d.slot == event.slot),
            None,
        )
        if device is None:
            return

        # Elimination: if feature_index matches a known resolved feature, this is not x1D4B
        if event.feature_index in device.available_features.values():
            return

        if len(event.payload) < 2 or event.payload[1] != 0x01:
            return

        log.debug(f"x1D4B reconnect on wpid=0x{device.wpid:04X}")
        self._topics.hid_event.publish(
            DeviceConnectedEvent(
                slot=device.slot,
                pid=device.pid,
                link_established=True,
                wpid=device.wpid,
            )
        )
