import logging

from ...event.divert_event import DivertEvent
from ...event.hidpp_error_event import HidppErrorEvent
from ...hidpp.constants import (
    FEATURE_REPROG_CONTROLS_V4,
    FEATURE_ROOT,
    HOST_SWITCH_CIDS,
    KEY_FLAG_DIVERTABLE,
    KEY_FLAG_PERSISTENTLY_DIVERTABLE,
)
from ...model.logi_device import LogiDevice
from ...subscriber.task.info_task import InfoTask
from ...topic.topic import Topic
from .constants import FIND_DIVERTABLE_CIDS_SW_ID

log = logging.getLogger(__name__)


class FindDivertableCidsTask(InfoTask):
    """Queries REPROG_CONTROLS_V4 to find divertable ES key CIDs, then publishes DivertEvent."""

    def __init__(self, device: LogiDevice, topics: dict[str, Topic]) -> None:
        super().__init__("find_divertable_cids", device, topics, FEATURE_ROOT, FIND_DIVERTABLE_CIDS_SW_ID)

    def doTask(self) -> None:
        reprog_idx = self._device.available_features.get(FEATURE_REPROG_CONTROLS_V4)
        if reprog_idx is None:
            if "resolve_reprog" not in self._device.pending_steps:
                self._device.pending_steps.discard(self._step_name)
            return

        # fn[0] getCount
        self._send_request(request_id=(reprog_idx << 8) | 0x00)
        response = self._wait_response()
        if response is None or isinstance(response, HidppErrorEvent):
            return
        count = response.payload[0]

        divertable: set[int] = set()
        persistently_divertable: set[int] = set()
        all_read = True
        for index in range(count):
            # fn[1] getCidInfo(index)
            self._send_request(index, request_id=(reprog_idx << 8) | 0x10)
            response = self._wait_response()
            if response is None or isinstance(response, HidppErrorEvent):
                all_read = False
                continue
            cid = (response.payload[0] << 8) | response.payload[1]
            if cid not in HOST_SWITCH_CIDS:
                continue
            flags = response.payload[4]
            if flags & KEY_FLAG_DIVERTABLE:
                divertable.add(cid)
            if flags & KEY_FLAG_PERSISTENTLY_DIVERTABLE:
                persistently_divertable.add(cid)

        self._device.divertable_cids = divertable
        self._device.persistently_divertable_cids = persistently_divertable

        if all_read:
            self._device.pending_steps.discard(self._step_name)
        else:
            log.warning("slot=%d: incomplete CID scan, will retry on reconnection", self._device.slot)

        if divertable:
            log.info("slot=%d: divertable ES CIDs: %s", self._device.slot, {f"0x{c:04X}" for c in divertable})
            if persistently_divertable:
                log.info(
                    "slot=%d: persistently divertable ES CIDs: %s",
                    self._device.slot,
                    {f"0x{c:04X}" for c in persistently_divertable},
                )
            self._topics["divert_topic"].publish(
                DivertEvent(
                    slot=self._device.slot,
                    pid=self._device.pid,
                    wpid=self._device.wpid,
                    cids=divertable,
                )
            )
