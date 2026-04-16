import logging

from ..event.host_change_event import HostChangeEvent
from ..event.write_event import WriteEvent
from ..hidpp.constants import (
    CHANGE_HOST_FN_SET,
    FEATURE_CHANGE_HOST,
    SW_ID_HOST_CHANGE,
)
from ..hidpp.protocol import build_msg, pack_params
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..topic.topics import Topics

log = logging.getLogger(__name__)


class HostChangeSubscriber(Subscriber):
    def __init__(self, device_registry: LogiDeviceRegistry, topics: Topics):
        self._device_registry = device_registry
        self._topics = topics
        topics.hid_event.subscribe(self)

    def notify(self, event) -> None:
        if not isinstance(event, HostChangeEvent):
            return

        for device in self._device_registry.all_entries():
            change_host_idx = device.available_features.get(FEATURE_CHANGE_HOST)
            if change_host_idx is None:
                continue

            request_id = (change_host_idx << 8) | (CHANGE_HOST_FN_SET & 0xF0) | SW_ID_HOST_CHANGE
            params = pack_params((event.target_host,))
            msg = build_msg(device.slot, request_id, params)
            self._topics.write.publish(WriteEvent(slot=device.slot, pid=device.pid, hid_message=msg))
            log.info("Sending host change to %s (slot=%d) -> host %d", device.name, device.slot, event.target_host + 1)
