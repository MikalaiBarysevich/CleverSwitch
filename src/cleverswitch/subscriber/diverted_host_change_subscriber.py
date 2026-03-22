import logging

from ..event.hidpp_notification_event import HidppNotificationEvent
from ..event.write_event import WriteEvent
from ..hidpp.constants import CHANGE_HOST_FN_SET, FEATURE_CHANGE_HOST, FEATURE_REPROG_CONTROLS_V4, HOST_SWITCH_CIDS, SW_ID_HOST_CHANGE
from ..hidpp.protocol import build_msg, pack_params
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..topic.topic import Topic

log = logging.getLogger(__name__)


class DivertedHostChangeSubscriber(Subscriber):

    def __init__(self, device_registry: LogiDeviceRegistry, topics: dict[str, Topic]):
        self._device_registry = device_registry
        self._topics = topics
        topics["event_topic"].subscribe(self)

    def notify(self, event) -> None:
        if not isinstance(event, HidppNotificationEvent):
            return
        if event.function != 0:
            return

        # Find source device to check if this is a REPROG_CONTROLS_V4 notification
        source = None
        for device in self._device_registry.all_entries():
            if device.pid == event.pid and device.slot == event.slot:
                source = device
                break

        if source is None:
            return

        reprog_idx = source.available_features.get(FEATURE_REPROG_CONTROLS_V4)
        if reprog_idx is None or event.feature_index != reprog_idx:
            return

        cid = (event.payload[0] << 8) | event.payload[1]
        if cid not in HOST_SWITCH_CIDS:
            return

        target_host = HOST_SWITCH_CIDS[cid]
        log.info("Diverted host change detected from %s (slot=%d) CID=0x%04X -> host %d", source.name, source.slot, cid, target_host + 1)

        # Send to ALL devices including source (source didn't switch because key was diverted)
        for device in self._device_registry.all_entries():
            change_host_idx = device.available_features.get(FEATURE_CHANGE_HOST)
            if change_host_idx is None:
                continue

            request_id = (change_host_idx << 8) | (CHANGE_HOST_FN_SET & 0xF0) | SW_ID_HOST_CHANGE
            params = pack_params((target_host,))
            msg = build_msg(device.slot, request_id, params)
            self._topics["write_topic"].publish(WriteEvent(slot=device.slot, pid=device.pid, hid_message=msg))
            log.info("Sending host change to %s (slot=%d) -> host %d", device.name, device.slot, target_host + 1)
