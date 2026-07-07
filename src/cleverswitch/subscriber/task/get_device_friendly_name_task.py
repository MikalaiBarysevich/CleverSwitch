import logging

from ...event.hidpp_error_event import HidppErrorEvent
from ...hidpp.constants import FEATURE_DEVICE_FRIENDLY_NAME, FEATURE_ROOT
from ...model.logi_device import LogiDevice
from ...subscriber.task.info_task import InfoTask
from ...topic.topics import Topics
from ...util.util import decode_string_response
from .constants import GET_DEVICE_FRIENDLY_NAME_SW_ID, Task

log = logging.getLogger(__name__)


class GetDeviceFriendlyNameTask(InfoTask):
    """Reads device friendly name via x0007 getFriendlyNameLen + getFriendlyName."""

    def __init__(self, device: LogiDevice, topics: Topics) -> None:
        super().__init__(
            Task.Name.GET_DEVICE_FRIENDLY_NAME, device, topics, FEATURE_ROOT, GET_DEVICE_FRIENDLY_NAME_SW_ID
        )

    def doTask(self) -> None:
        idx = self._device.available_features.get(FEATURE_DEVICE_FRIENDLY_NAME)
        if idx is None:
            if Task.Feature.Name.FRIENDLY_NAME not in self._device.pending_steps:
                log.debug(f"wpid=0x{self._device.wpid:04X}: x0007 not supported, skipping friendly name")
                self._device.pending_steps.discard(self._step_name)
            return

        if self._device.friendly_name is not None:
            self._device.pending_steps.discard(self._step_name)
            return

        # fn[0] getFriendlyNameLen
        self._send_request(request_id=(idx << 8) | 0x00)
        response = self._wait_response()
        if response is None or isinstance(response, HidppErrorEvent):
            self._device.friendly_name = None
            return
        name_len = response.payload[0]
        if name_len == 0:
            self._device.pending_steps.discard(self._step_name)
            return

        # fn[1] getFriendlyName(byteIndex)
        # response payload byte 0 echoes byteIndex; bytes 1..15 carry up to 15 name bytes
        chars: list[int] = []
        while len(chars) < name_len:
            self._send_request(len(chars), request_id=(idx << 8) | 0x10)
            response = self._wait_response()
            if response is None or isinstance(response, HidppErrorEvent):
                break
            remaining = min(15, name_len - len(chars))
            chunk = response.payload[1 : 1 + remaining]
            if not chunk:
                break
            chars.extend(chunk)

        if len(chars) == name_len:
            self._device.friendly_name = decode_string_response(bytes(chars))
            log.debug(f"wpid=0x{self._device.wpid:04X}: friendly_name={self._device.friendly_name}")
            self._device.pending_steps.discard(self._step_name)
        else:
            self._device.friendly_name = None
