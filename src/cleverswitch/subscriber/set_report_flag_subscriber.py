import logging
import struct

from ..event.set_report_flag_event import SetReportFlagEvent
from ..event.write_event import WriteEvent
from ..hidpp.constants import (
    ANALYTICS_BYTE9,
    FEATURE_REPROG_CONTROLS_V4,
    KEY_FLAG_ANALYTICS,
    KEY_FLAG_DIVERTABLE,
    KEY_FLAG_PERSISTENTLY_DIVERTABLE,
    MAP_FLAG_DIVERTED,
    MAP_FLAG_PERSISTENTLY_DIVERTED,
    SW_ID_DIVERT,
)
from ..hidpp.protocol import build_msg
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..topic.topics import Topics

log = logging.getLogger(__name__)


class SetReportFlagSubscriber(Subscriber):
    def __init__(self, device_registry: LogiDeviceRegistry, topics: Topics):
        self._device_registry = device_registry
        self._topics = topics
        topics.flags.subscribe(self)

    def notify(self, event) -> None:
        if not isinstance(event, SetReportFlagEvent):
            return

        device = self._device_registry.get_by_wpid(event.wpid)
        if device is None:
            log.warning(f"device wpid=0x{event.wpid:04X} not found")
            return

        reprog_idx = device.available_features.get(FEATURE_REPROG_CONTROLS_V4)
        if reprog_idx is None:
            log.warning(f"wpid=0x{event.wpid:04X} has no REPROG_CONTROLS_V4")
            return

        if not device.supported_flags & {KEY_FLAG_ANALYTICS, KEY_FLAG_DIVERTABLE}:
            log.warning(f"wpid=0x{event.wpid:04X} has no reprog flags")
            return

        for cid in event.cids:
            if KEY_FLAG_ANALYTICS in device.supported_flags:
                params = struct.pack("!HBHB", cid, 0x00, 0x0000, ANALYTICS_BYTE9)
            else:
                # Temporary divert: valid + action
                if event.enable:
                    bfield = MAP_FLAG_DIVERTED << 1 | MAP_FLAG_DIVERTED
                else:
                    bfield = MAP_FLAG_DIVERTED << 1
                # Persistent divert if the CID supports it
                if KEY_FLAG_PERSISTENTLY_DIVERTABLE in device.supported_flags:
                    bfield |= MAP_FLAG_PERSISTENTLY_DIVERTED << 1
                    if event.enable:
                        bfield |= MAP_FLAG_PERSISTENTLY_DIVERTED
                params = struct.pack("!HBH", cid, bfield, 0)

            request_id = (reprog_idx << 8) | 0x30 | SW_ID_DIVERT
            msg = build_msg(event.slot, request_id, params)
            self._topics.write.publish(WriteEvent(slot=event.slot, pid=event.pid, hid_message=msg))
            action = (
                "Enabling analytics for"
                if KEY_FLAG_ANALYTICS in device.supported_flags
                else ("Setting divert" if event.enable else "Unsetting divert")
            )
            log.debug(f"{action} CID 0x{cid:04X} on wpid=0x{event.wpid:04X}")
