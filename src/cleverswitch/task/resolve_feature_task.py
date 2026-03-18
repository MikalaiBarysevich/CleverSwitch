import logging

from ..hidpp.constants import FEATURE_ROOT
from ..model.logi_device import LogiDevice
from ..task.info_task import InfoTask
from ..topic.topic import Topic

log = logging.getLogger(__name__)


class ResolveFeatureTask(InfoTask):
    """Resolves a single HID++ 2.0 feature index via ROOT GetFeature."""

    def __init__(
        self, sw_id: int, step_name: str, device: LogiDevice, topics: dict[str, Topic], feature_code: int,
    ) -> None:
        super().__init__(sw_id, step_name, device, topics)
        self._feature_code = feature_code

    def run(self) -> None:
        request_id = (FEATURE_ROOT << 8) | 0x00
        response = self._send_request(request_id, self._feature_code >> 8, self._feature_code & 0xFF, 0x00)
        if response is not None and response.payload[0] != 0x00:
            feat_idx = response.payload[0]
            self._device.available_features[self._feature_code] = feat_idx
            log.info("slot=%d: feature 0x%04X at index %d", self._device.slot, self._feature_code, feat_idx)
        else:
            log.info("slot=%d: feature 0x%04X not supported", self._device.slot, self._feature_code)
        self._device.completed_steps.add(self._step_name)
