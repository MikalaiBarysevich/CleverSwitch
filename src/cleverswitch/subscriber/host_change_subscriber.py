import logging

from ..event.hidpp_notification_event import HidppNotificationEvent
from ..event.write_event import WriteEvent
from ..hidpp.constants import CHANGE_HOST_FN_SET, FEATURE_CHANGE_HOST, SW_ID_HOST_CHANGE
from ..hidpp.protocol import build_msg, pack_params
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..topic.topic import Topic

log = logging.getLogger(__name__)


class HostChangeSubscriber(Subscriber):

    def __init__(self, device_registry: LogiDeviceRegistry, topics: dict[str, Topic]):
        self._device_registry = device_registry
        self._topics = topics
        topics["event_topic"].subscribe(self)

    def notify(self, event) -> None:
        if not isinstance(event, HidppNotificationEvent):
            return

        # Find source device to check if this notification is from CHANGE_HOST feature
        source = None
        for device in self._device_registry.all_entries():
            if device.pid == event.pid and device.slot == event.slot:
                source = device
                break

        if source is None:
            return

        change_host_idx = source.available_features.get(FEATURE_CHANGE_HOST)
        if change_host_idx is None or event.feature_index != change_host_idx:
            return

        target_host = event.payload[0]
        log.info("Host change detected from %s (slot=%d) -> host %d", source.name, source.slot, target_host)

        for device in self._device_registry.all_entries():
            # Source already switched on its own
            if device.pid == event.pid and device.slot == event.slot:
                continue

            dev_change_host_idx = device.available_features.get(FEATURE_CHANGE_HOST)
            if dev_change_host_idx is None:
                continue

            request_id = (dev_change_host_idx << 8) | (CHANGE_HOST_FN_SET & 0xF0) | SW_ID_HOST_CHANGE
            params = pack_params((target_host,))
            msg = build_msg(device.slot, request_id, params)
            self._topics["write_topic"].publish(WriteEvent(slot=device.slot, pid=device.pid, hid_message=msg))
            log.info("Sending host change to %s (slot=%d) -> host %d", device.name, device.slot, target_host)
