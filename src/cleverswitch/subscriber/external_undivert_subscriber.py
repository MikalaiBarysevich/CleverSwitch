import logging

from ..event.divert_event import DivertEvent
from ..event.external_undivert_event import ExternalUndivertEvent
from ..hidpp.constants import FEATURE_REPROG_CONTROLS_V4
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..topic.topics import Topics

log = logging.getLogger(__name__)


class ExternalUndivertSubscriber(Subscriber):
    def __init__(self, device_registry: LogiDeviceRegistry, topics: Topics):
        self._device_registry = device_registry
        self._topics = topics
        topics.hid_event.subscribe(self)

    def notify(self, event) -> None:
        if not isinstance(event, ExternalUndivertEvent):
            return

        # Find the device by slot to verify feature_index matches REPROG_CONTROLS_V4
        device = None
        for entry in self._device_registry.all_entries():
            if entry.slot == event.slot:
                device = entry
                break

        if device is None:
            return

        reprog_idx = device.available_features.get(FEATURE_REPROG_CONTROLS_V4)
        if reprog_idx is None or reprog_idx != event.feature_index:
            return

        if event.cid not in device.divertable_cids:
            return

        log.info("External undivert detected: CID 0x%04X on slot=%d, re-diverting", event.cid, event.slot)

        self._topics.divert.publish(
            DivertEvent(
                slot=event.slot,
                pid=device.pid,
                wpid=device.wpid,
                cids={event.cid},
            )
        )
