import logging

from ...event.hidpp_error_event import HidppErrorEvent
from ...hidpp.constants import FEATURE_DEVICE_TYPE_AND_NAME, FEATURE_ROOT
from ...model.logi_device import LogiDevice
from ...subscriber.task.feature.cid_reporting_feature_task import CidReportingFeatureTask
from ...subscriber.task.info_task import InfoTask
from ...topic.topics import Topics
from .constants import GET_DEVICE_TYPE_SW_ID, Task

log = logging.getLogger(__name__)


class GetDeviceTypeTask(InfoTask):
    """Reads device type via x0005 getDeviceType."""

    def __init__(self, device: LogiDevice, topics: Topics) -> None:
        super().__init__(Task.Name.GET_DEVICE_TYPE, device, topics, FEATURE_ROOT, GET_DEVICE_TYPE_SW_ID)

    def doTask(self) -> None:
        if self._device.role is not None:
            self._device.pending_steps.discard(self._step_name)
            return

        type_and_name_idx = self._device.available_features.get(FEATURE_DEVICE_TYPE_AND_NAME)
        if type_and_name_idx is None:
            if Task.Feature.Name.NAME_AND_TYPE not in self._device.pending_steps:
                log.info("slot=%d: DEVICE_TYPE_AND_NAME not supported, skipping type", self._device.slot)
                self._device.pending_steps.discard(self._step_name)
            return

        # fn[2] getDeviceType
        self._send_request(request_id=(type_and_name_idx << 8) | 0x20)
        response = self._wait_response()
        if response is None:
            return  # timeout — keep step pending for retry
        if not isinstance(response, HidppErrorEvent):
            device_type = response.payload[0]
            self._device.role = "keyboard" if device_type == 0 else "mouse"
            log.info("slot=%d: type=%s", self._device.slot, self._device.role)

        self._device.pending_steps.discard(self._step_name)

    def _fire_dependent_steps(self):
        if self._device.role != "keyboard" or Task.Feature.Name.CID_REPORTING not in self._device.pending_steps:
            return
        CidReportingFeatureTask(self._device, self._topics).start()
