import logging

from ...event.hidpp_error_event import HidppErrorEvent
from ...event.set_report_flag_event import SetReportFlagEvent
from ...hidpp.constants import (
    FEATURE_REPROG_CONTROLS_V4,
    FEATURE_ROOT,
    HOST_SWITCH_CIDS,
    KEY_FLAG_ANALYTICS,
    KEY_FLAG_DIVERTABLE,
    KEY_FLAG_PERSISTENTLY_DIVERTABLE,
)
from ...model.logi_device import LogiDevice
from ...subscriber.task.info_task import InfoTask
from ...topic.topics import Topics
from .constants import FIND_ES_CIDS_FLAGS_SW_ID, Task

log = logging.getLogger(__name__)


class FindESCidsFlagsTask(InfoTask):
    """Queries REPROG_CONTROLS_V4 to find divertable ES key CIDs, then publishes DivertEvent."""

    def __init__(self, device: LogiDevice, topics: Topics) -> None:
        super().__init__(Task.Name.FIND_ES_CIDS_FLAGS, device, topics, FEATURE_ROOT, FIND_ES_CIDS_FLAGS_SW_ID)

    def doTask(self) -> None:
        reprog_idx = self._device.available_features.get(FEATURE_REPROG_CONTROLS_V4)
        if reprog_idx is None:
            if Task.Feature.Name.CID_REPORTING not in self._device.pending_steps:
                self._device.pending_steps.discard(self._step_name)
            return

        # fn[0] getCount
        self._send_request(request_id=(reprog_idx << 8) | 0x00)
        response = self._wait_response()
        if response is None or isinstance(response, HidppErrorEvent):
            return
        count = response.payload[0]

        cid_seen = False
        for index in range(count):
            # fn[1] getCidInfo(index)
            self._send_request(index, request_id=(reprog_idx << 8) | 0x10)
            response = self._wait_response()
            if response is None or isinstance(response, HidppErrorEvent):
                continue
            cid = (response.payload[0] << 8) | response.payload[1]
            if cid not in HOST_SWITCH_CIDS:
                continue
            flags = response.payload[4]
            if flags & KEY_FLAG_DIVERTABLE:
                self._device.supported_flags.add(KEY_FLAG_DIVERTABLE)
            if flags & KEY_FLAG_PERSISTENTLY_DIVERTABLE:
                self._device.supported_flags.add(KEY_FLAG_PERSISTENTLY_DIVERTABLE)
            if flags & KEY_FLAG_ANALYTICS:
                self._device.supported_flags.add(KEY_FLAG_ANALYTICS)
            cid_seen = True
            break

        if not cid_seen:
            log.warning("Failed to collect ES keys info. Switching may not work. Reconnection required")
            return

        self._device.pending_steps.discard(self._step_name)

        if (
            KEY_FLAG_ANALYTICS not in self._device.supported_flags
            and KEY_FLAG_DIVERTABLE not in self._device.supported_flags
        ):
            log.error(
                f"0x{self._device.wpid:04X}: No analytics or divertable ES CIDs found — host switching unavailable"
            )
            return

        self._topics.flags.publish(
            SetReportFlagEvent(
                slot=self._device.slot,
                pid=self._device.pid,
                wpid=self._device.wpid,
            )
        )

        flags_str = ", ".join(f"0x{x:04X}" for x in sorted(self._device.supported_flags))
        log.debug(f"0x{self._device.wpid:04X}: supported flags: {flags_str}")
