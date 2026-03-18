import logging

from ..hidpp.constants import FEATURE_DEVICE_TYPE_AND_NAME
from ..model.logi_device import LogiDevice
from ..task.info_task import InfoTask
from ..topic.topic import Topic

log = logging.getLogger(__name__)

STEP_NAME = "get_device_type"


class GetDeviceTypeTask(InfoTask):
    """Resolves x0005 feature index (if needed) and reads device type."""

    def __init__(self, sw_id: int, device: LogiDevice, topics: dict[str, Topic]) -> None:
        super().__init__(sw_id, STEP_NAME, device, topics)

    def run(self) -> None:
        x0005_idx = self._device.available_features.get(FEATURE_DEVICE_TYPE_AND_NAME)
        if x0005_idx is None:
            if "resolve_x0005" in self._device.completed_steps:
                log.info("slot=%d: DEVICE_TYPE_AND_NAME not supported, skipping type", self._device.slot)
                self._device.completed_steps.add(self._step_name)
            return

        if self._device.role is not None:
            self._device.completed_steps.add(self._step_name)
            return

        # fn[2] getDeviceType
        request_id = (x0005_idx << 8) | 0x20
        response = self._send_request(request_id)
        if response is not None:
            device_type = response.payload[0]
            self._device.role = "keyboard" if device_type == 0 else "mouse"
            log.info("slot=%d: type=%s", self._device.slot, self._device.role)
        self._device.completed_steps.add(self._step_name)
