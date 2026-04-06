import logging

from ....event.hidpp_error_event import HidppErrorEvent
from ....model.logi_device import LogiDevice
from ....subscriber.task.info_task import InfoTask
from ....topic.topics import Topics

log = logging.getLogger(__name__)


class FeatureTask(InfoTask):
    def __init__(
        self,
        step_name: str,
        device: LogiDevice,
        topics: Topics,
        feature_code: int,
        sw_id: int,
    ) -> None:
        super().__init__(step_name, device, topics, 0x0000, sw_id)  # ROOT GetFeature: feat_idx=0, fn=0
        self._feature_code = feature_code
        # self._on_resolved = on_resolved or []

    def doTask(self) -> None:
        if self._feature_code in self._device.available_features.values():
            log.debug("Feature 0x%04X already resolved", self._device.slot)
            self._fire_dependent_steps()
            return

        self._send_request(self._feature_code >> 8, self._feature_code & 0xFF, 0x00)

        event = self._wait_response()
        if event is None:
            log.warning("Timeout resolving feature 0x%04X for slot=%d", self._feature_code, self._device.slot)
            return

        if isinstance(event, HidppErrorEvent):
            log.warning(
                "Error resolving feature 0x%04X for slot=%d: error=0x%02X",
                self._feature_code,
                self._device.slot,
                event.error_code,
            )
            return

        if event.payload[0] != 0x00:
            feat_idx = event.payload[0]
            self._device.available_features[self._feature_code] = feat_idx
            log.info("slot=%d: feature 0x%04X at index %d", self._device.slot, self._feature_code, feat_idx)
        else:
            log.info("slot=%d: feature 0x%04X not supported", self._device.slot, self._feature_code)

        self._device.pending_steps.discard(self._step_name)
