import logging

from ..hidpp.constants import FEATURE_DEVICE_TYPE_AND_NAME
from ..model.logi_device import LogiDevice
from ..task.info_task import InfoTask
from ..topic.topic import Topic

log = logging.getLogger(__name__)

STEP_NAME = "get_device_name"


class GetDeviceNameTask(InfoTask):
    """Resolves x0005 feature index (if needed) and reads device name."""

    def __init__(self, sw_id: int, device: LogiDevice, topics: dict[str, Topic]) -> None:
        super().__init__(sw_id, STEP_NAME, device, topics)

    def run(self) -> None:
        x0005_idx = self._device.available_features.get(FEATURE_DEVICE_TYPE_AND_NAME)
        if x0005_idx is None:
            if "resolve_x0005" in self._device.completed_steps:
                log.info("slot=%d: DEVICE_TYPE_AND_NAME not supported, skipping name", self._device.slot)
                self._device.completed_steps.add(self._step_name)
            return

        if self._device.name is not None:
            self._device.completed_steps.add(self._step_name)
            return

        # fn[0] getDeviceNameCount
        request_id = (x0005_idx << 8) | 0x00
        response = self._send_request(request_id)
        if response is None:
            self._device.completed_steps.add(self._step_name)
            return
        name_len = response.payload[0]
        if name_len == 0:
            self._device.completed_steps.add(self._step_name)
            return

        # fn[1] getDeviceName(charIndex)
        chars: list[int] = []
        while len(chars) < name_len:
            request_id = (x0005_idx << 8) | 0x10
            response = self._send_request(request_id, len(chars))
            if response is None:
                break
            remaining = name_len - len(chars)
            chunk = response.payload[:remaining]
            if not chunk:
                break
            chars.extend(chunk)

        if chars:
            self._device.name = bytes(chars).decode("utf-8", errors="replace")
            log.info("slot=%d: name=%s", self._device.slot, self._device.name)
        self._device.completed_steps.add(self._step_name)
