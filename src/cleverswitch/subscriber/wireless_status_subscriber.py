import logging

from ..event.divert_event import DivertEvent
from ..event.hidpp_notification_event import HidppNotificationEvent
from ..hidpp.constants import FEATURE_REPROG_CONTROLS_V4
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..topic.topic import Topic

log = logging.getLogger(__name__)


class WirelessStatusSubscriber(Subscriber):
    def __init__(self, device_registry: LogiDeviceRegistry, topics: dict[str, Topic]):
        self._device_registry = device_registry
        self._topics = topics
        topics["event_topic"].subscribe(self)

    def notify(self, event) -> None:
        if not isinstance(event, HidppNotificationEvent):
            return

        if event.function != 0:
            return

        # Find device by slot and pid
        device = None
        for entry in self._device_registry.all_entries():
            if entry.pid == event.pid and entry.slot == event.slot:
                device = entry
                break

        if device is None:
            return

        # Elimination: if feature_index matches a known resolved feature, this is not x1D4B
        if event.feature_index in device.available_features.values():
            return

        # x1D4B payload check: payload[1] == 0x01 means software reconfiguration needed
        if len(event.payload) < 2 or event.payload[1] != 0x01:
            return

        if not device.divertable_cids or FEATURE_REPROG_CONTROLS_V4 not in device.available_features:
            return

        name = f"'{device.name}'" if device.name else f"slot={device.slot}"
        log.info("x1D4B reconfiguration request for %s, re-diverting", name)

        self._topics["divert_topic"].publish(
            DivertEvent(
                slot=device.slot,
                pid=device.pid,
                wpid=device.wpid,
                cids=device.divertable_cids,
            )
        )
