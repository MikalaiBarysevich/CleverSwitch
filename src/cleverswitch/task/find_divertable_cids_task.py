import logging

from ..event.divert_event import DivertEvent
from ..hidpp.constants import (
    FEATURE_REPROG_CONTROLS_V4,
    HOST_SWITCH_CIDS,
    KEY_FLAG_DIVERTABLE,
    KEY_FLAG_PERSISTENTLY_DIVERTABLE,
)
from ..model.logi_device import LogiDevice
from ..task.info_task import InfoTask
from ..topic.topic import Topic

log = logging.getLogger(__name__)

STEP_NAME = "find_divertable_cids"


class FindDivertableCidsTask(InfoTask):
    """Queries REPROG_CONTROLS_V4 to find divertable ES key CIDs, then publishes DivertEvent."""

    def __init__(self, sw_id: int, device: LogiDevice, topics: dict[str, Topic]) -> None:
        super().__init__(sw_id, STEP_NAME, device, topics)

    def run(self) -> None:
        reprog_idx = self._device.available_features.get(FEATURE_REPROG_CONTROLS_V4)
        if reprog_idx is None:
            if "resolve_reprog" in self._device.completed_steps:
                # Feature genuinely not supported — won't change on retry
                self._device.completed_steps.add(self._step_name)
            return

        # fn[0] getCount
        request_id = (reprog_idx << 8) | 0x00
        response = self._send_request(request_id)
        if response is None:
            self._device.completed_steps.add(self._step_name)
            return
        count = response.payload[0]

        divertable: set[int] = set()
        persistently_divertable: set[int] = set()
        for index in range(count):
            # fn[1] getCidInfo(index)
            request_id = (reprog_idx << 8) | 0x10
            response = self._send_request(request_id, index)
            if response is None:
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
        self._device.completed_steps.add(self._step_name)

        if divertable:
            log.info("slot=%d: divertable ES CIDs: %s", self._device.slot, {f"0x{c:04X}" for c in divertable})
            if persistently_divertable:
                log.info(
                    "slot=%d: persistently divertable ES CIDs: %s",
                    self._device.slot, {f"0x{c:04X}" for c in persistently_divertable},
                )
            self._topics["divert_topic"].publish(DivertEvent(
                slot=self._device.slot,
                pid=self._device.pid,
                wpid=self._device.wpid,
                cids=divertable,
            ))
