import logging

from ..event.hidpp_notification_event import HidppNotificationEvent
from ..event.host_change_event import HostChangeEvent
from ..hidpp.constants import FEATURE_REPROG_CONTROLS_V4, HOST_SWITCH_CIDS
from ..model.logi_device import LogiDevice
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..topic.topics import Topics

log = logging.getLogger(__name__)

_DIVERTED_BUTTONS = 0
_ANALYTICS_KEY = 2
_PRESSED = 0x01


class EasySwitchKeySubscriber(Subscriber):
    """Translates an Easy-Switch key press reported by x1B04 into a HostChangeEvent.

    A diverted press arrives as fn=0 and an analytics press as fn=2 with payload[2]=0x01; both carry the
    CID in payload[0:2]. The parser is stateless and cannot map a feature index back to its feature code,
    so the match against the device's resolved x1B04 index happens here.
    """

    def __init__(self, device_registry: LogiDeviceRegistry, topics: Topics):
        self._device_registry = device_registry
        self._topics = topics
        topics.hid_event.subscribe(self)

    def notify(self, event) -> None:
        if not isinstance(event, HidppNotificationEvent):
            return
        if event.function not in (_DIVERTED_BUTTONS, _ANALYTICS_KEY) or len(event.payload) < 3:
            return

        device = self._find_device(event)
        if device is None or device.available_features.get(FEATURE_REPROG_CONTROLS_V4) != event.feature_index:
            return

        cid = (event.payload[0] << 8) | event.payload[1]
        if cid not in HOST_SWITCH_CIDS:
            return
        if event.function == _ANALYTICS_KEY and event.payload[2] != _PRESSED:
            return

        self._topics.hid_event.publish(
            HostChangeEvent(slot=event.slot, pid=event.pid, target_host=HOST_SWITCH_CIDS[cid])
        )

    def _find_device(self, event: HidppNotificationEvent) -> LogiDevice | None:
        for entry in self._device_registry.all_entries():
            if entry.pid == event.pid and entry.slot == event.slot:
                return entry
        return None
