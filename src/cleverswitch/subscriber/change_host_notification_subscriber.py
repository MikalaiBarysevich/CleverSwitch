import logging

from ..event.hidpp_notification_event import HidppNotificationEvent
from ..event.host_change_event import HostChangeEvent
from ..hidpp.constants import FEATURE_CHANGE_HOST, HOST_SWITCH_CIDS
from ..model.logi_device import LogiDevice
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..topic.topics import Topics

log = logging.getLogger(__name__)

VALID_HOSTS = frozenset(HOST_SWITCH_CIDS.values())


class ChangeHostNotificationSubscriber(Subscriber):
    """Translates the x1814 Easy-Switch announcement into a HostChangeEvent.

    Devices whose Easy-Switch CIDs never deliver an x1B04 notification (MX Keys S and
    friends) announce the press on the CHANGE_HOST feature itself: fn=0, sw_id=0,
    payload[0]=departing host, payload[1]=target host, both 0-based. The parser is
    stateless and cannot map a feature index back to its feature code, so the match
    against the device's resolved x1814 index happens here.
    """

    def __init__(self, device_registry: LogiDeviceRegistry, topics: Topics):
        self._device_registry = device_registry
        self._topics = topics
        topics.hid_event.subscribe(self)

    def notify(self, event) -> None:
        if not isinstance(event, HidppNotificationEvent):
            return

        if event.function != 0:
            return

        device = self._find_device(event)
        if device is None:
            return

        if device.available_features.get(FEATURE_CHANGE_HOST) != event.feature_index:
            return

        if len(event.payload) < 2:
            return

        target_host = event.payload[1]
        if target_host not in VALID_HOSTS:
            log.warning(f"'{device.display_name}' announced unknown target host {target_host}")
            return

        log.info(f"'{device.display_name}' switched to host {target_host + 1}")
        self._topics.hid_event.publish(HostChangeEvent(slot=device.slot, pid=device.pid, target_host=target_host))

    def _find_device(self, event: HidppNotificationEvent) -> LogiDevice | None:
        for entry in self._device_registry.all_entries():
            if entry.pid == event.pid and entry.slot == event.slot:
                return entry
        return None
