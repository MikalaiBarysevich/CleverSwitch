import logging
import struct
from threading import Timer

from ..event.hidpp_response_event import HidppResponseEvent
from ..event.set_report_flag_event import SetReportFlagEvent
from ..event.write_event import WriteEvent
from ..hidpp.constants import (
    FEATURE_REPROG_CONTROLS_V4,
    SW_ID_DIVERT,
)
from ..hidpp.protocol import build_msg
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..topic.topics import Topics

log = logging.getLogger(__name__)

_VERIFY_DELAY_S = 3.0
_GET_CID_REPORTING_FN = 0x20  # fn=2, upper nibble


class VerifyCidFlagSubscriber(Subscriber):
    """After setCidReporting, queries getCidReporting to verify flags are still set.

    Detects when another application (e.g. Logi Options+) overwrites the
    analytics/divert flags that CleverSwitch set.
    """

    def __init__(self, device_registry: LogiDeviceRegistry, topics: Topics):
        self._device_registry = device_registry
        self._topics = topics
        topics.flags.subscribe(self)
        topics.hid_event.subscribe(self)

    def notify(self, event) -> None:
        if isinstance(event, SetReportFlagEvent):
            self._schedule_verify(event)
        elif isinstance(event, HidppResponseEvent):
            self._check_response(event)

    def _schedule_verify(self, event: SetReportFlagEvent) -> None:
        device = self._device_registry.get_by_wpid(event.wpid)
        if device is None:
            return

        reprog_idx = device.available_features.get(FEATURE_REPROG_CONTROLS_V4)
        if reprog_idx is None:
            return

        timer = Timer(
            _VERIFY_DELAY_S,
            self._send_get_cid_reporting,
            args=(event.slot, event.pid, event.wpid, reprog_idx, event.cids),
        )
        timer.daemon = True
        timer.start()

    def _send_get_cid_reporting(
        self, slot: int, pid: int, wpid: int, reprog_idx: int, cids: set[int]
    ) -> None:
        device = self._device_registry.get_by_wpid(wpid)
        if device is None or not device.connected:
            return

        for cid in cids:
            request_id = (reprog_idx << 8) | _GET_CID_REPORTING_FN | SW_ID_DIVERT
            params = struct.pack("!H", cid) + b"\x00" * 14
            msg = build_msg(slot, request_id, params)
            self._topics.write.publish(WriteEvent(slot=slot, pid=pid, hid_message=msg))

    def _check_response(self, event: HidppResponseEvent) -> None:
        if event.sw_id != SW_ID_DIVERT:
            return
        if event.function != 2:
            return

        # device = self._device_registry.get_by_wpid(event.pid)
        # if device is None:
        #     return

        # reprog_idx = device.available_features.get(FEATURE_REPROG_CONTROLS_V4)
        # if reprog_idx is None or reprog_idx != event.feature_index:
        #     return

        cid = (event.payload[0] << 8) | event.payload[1]
        # getCidReporting response: payload[2] bit 0 = divert, payload[5] bit 0 = analyticsKeyEvt
        divert_set = event.payload[2] & 0x01
        analytics_set = event.payload[5] & 0x01

        if analytics_set or divert_set:
            log.info(
                "Verify CID 0x%04X on slot=%d: OK (divert=%d analytics=%d)",
                cid, event.slot, int(bool(divert_set)), int(bool(analytics_set)),
            )
        else:
            log.warning(
                "Verify CID 0x%04X on slot=%d: FLAGS CLEARED by external app (divert=%d analytics=%d) — raw=%s",
                cid, event.slot, int(bool(divert_set)), int(bool(analytics_set)), event.payload.hex(),
            )
