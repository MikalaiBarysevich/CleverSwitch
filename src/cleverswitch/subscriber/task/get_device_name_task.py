import logging

from ...event.hidpp_error_event import HidppErrorEvent
from ...hidpp.constants import FEATURE_DEVICE_TYPE_AND_NAME, FEATURE_ROOT
from ...model.logi_device import LogiDevice
from ...subscriber.task.info_task import InfoTask
from ...topic.topic import Topic
from .constants import GET_DEVICE_NAME_SW_ID

log = logging.getLogger(__name__)


class GetDeviceNameTask(InfoTask):
    """Reads device name via x0005 getDeviceNameCount + getDeviceName."""

    def __init__(self, device: LogiDevice, topics: dict[str, Topic]) -> None:
        super().__init__("get_device_name", device, topics, FEATURE_ROOT, GET_DEVICE_NAME_SW_ID)

    def doTask(self) -> None:
        name_and_type_idx = self._device.available_features.get(FEATURE_DEVICE_TYPE_AND_NAME)
        if name_and_type_idx is None:
            if "resolve_x0005" not in self._device.pending_steps:
                log.info("slot=%d: DEVICE_TYPE_AND_NAME not supported, skipping name", self._device.slot)
                self._device.pending_steps.discard(self._step_name)
            return

        if self._device.name is not None:
            self._device.pending_steps.discard(self._step_name)
            return

        # fn[0] getDeviceNameCount
        self._send_request(request_id=(name_and_type_idx << 8) | 0x00)
        response = self._wait_response()
        if response is None or isinstance(response, HidppErrorEvent):
            self._device.name = None
            return
        name_len = response.payload[0]
        if name_len == 0:
            self._device.pending_steps.discard(self._step_name)
            return

        # fn[1] getDeviceName(charIndex)
        chars: list[int] = []
        while len(chars) < name_len:
            self._send_request(len(chars), request_id=(name_and_type_idx << 8) | 0x10)
            response = self._wait_response()
            if response is None or isinstance(response, HidppErrorEvent):
                break
            remaining = name_len - len(chars)
            chunk = response.payload[:remaining]
            if not chunk:
                break
            chars.extend(chunk)

        if len(chars) == name_len:
            self._device.name = bytes(chars).decode("utf-8", errors="replace")
            log.info("slot=%d: name=%s", self._device.slot, self._device.name)
            self._device.pending_steps.discard(self._step_name)
        else:
            self._device.name = None
