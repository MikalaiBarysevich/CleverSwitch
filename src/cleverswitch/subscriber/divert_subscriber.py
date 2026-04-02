import logging
import struct

from ..event.divert_event import DivertEvent
from ..event.write_event import WriteEvent
from ..hidpp.constants import (
    FEATURE_REPROG_CONTROLS_V4,
    MAP_FLAG_DIVERTED,
    MAP_FLAG_PERSISTENTLY_DIVERTED,
    SW_ID_DIVERT,
)
from ..hidpp.protocol import build_msg
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..topic.topic import Topic

log = logging.getLogger(__name__)


class DivertSubscriber(Subscriber):
    def __init__(self, device_registry: LogiDeviceRegistry, topics: dict[str, Topic]):
        self._device_registry = device_registry
        self._topics = topics
        topics["divert_topic"].subscribe(self)

    def notify(self, event) -> None:
        if not isinstance(event, DivertEvent):
            return

        device = self._device_registry.get_by_wpid(event.wpid)
        if device is None:
            log.warning("DivertSubscriber: device wpid=0x%04X not found", event.wpid)
            return

        reprog_idx = device.available_features.get(FEATURE_REPROG_CONTROLS_V4)
        if reprog_idx is None:
            log.warning("DivertSubscriber: slot=%d has no REPROG_CONTROLS_V4", event.slot)
            return

        for cid in event.cids:
            # Temporary divert: valid + action
            if event.divert:
                bfield = MAP_FLAG_DIVERTED << 1 | MAP_FLAG_DIVERTED
            else:
                bfield = MAP_FLAG_DIVERTED << 1

            # Persistent divert if the CID supports it
            if cid in device.persistently_divertable_cids:
                bfield |= MAP_FLAG_PERSISTENTLY_DIVERTED << 1
                if event.divert:
                    bfield |= MAP_FLAG_PERSISTENTLY_DIVERTED

            params = struct.pack("!HBH", cid, bfield, 0)
            request_id = (reprog_idx << 8) | 0x30 | SW_ID_DIVERT
            msg = build_msg(event.slot, request_id, params)
            self._topics["write_topic"].publish(WriteEvent(slot=event.slot, pid=event.pid, hid_message=msg))
            log.info("%s CID 0x%04X on slot=0x%04X", "Diverting" if event.divert else "Undiverting", cid, event.slot)
