import logging
import queue
import time
from abc import ABC, abstractmethod

from ..errors import ResponseTimeoutError
from ..event.hidpp_error_event import HidppErrorEvent
from ..event.hidpp_response_event import HidppResponseEvent
from ..event.write_event import WriteEvent
from ..hidpp.protocol import build_msg, pack_params
from ..model.logi_device import LogiDevice
from ..topic.topic import Topic

log = logging.getLogger(__name__)

RESPONSE_TIMEOUT = 2.0


class InfoTask(ABC):
    """Base class for device info tasks that send HID++ requests and wait for responses."""

    def __init__(self, sw_id: int, step_name: str, device: LogiDevice, topics: dict[str, Topic]) -> None:
        self._sw_id = sw_id
        self._step_name = step_name
        self._device = device
        self._topics = topics
        self._response_queue: queue.Queue = queue.Queue()

    @property
    def step_name(self) -> str:
        return self._step_name

    def forward_event(self, event: HidppResponseEvent | HidppErrorEvent) -> None:
        """Called by DeviceInfoSubscriber to forward matching events to this task."""
        self._response_queue.put(event)

    @abstractmethod
    def run(self) -> None:
        """Execute the task. Raises ResponseTimeoutError if a response times out."""

    def _send_request(self, request_id: int, *params) -> HidppResponseEvent | None:
        request_id = (request_id & 0xFFF0) | self._sw_id
        expected_feat_idx = (request_id >> 8) & 0xFF
        expected_fn = (request_id >> 4) & 0x0F
        params_bytes = pack_params(params)
        msg = build_msg(self._device.slot, request_id, params_bytes)
        self._topics["write_topic"].publish(
            WriteEvent(slot=self._device.slot, pid=self._device.pid, hid_message=msg)
        )
        return self._wait_response(expected_feat_idx, expected_fn)

    def _wait_response(self, feat_idx: int, function: int) -> HidppResponseEvent | None:
        deadline = time.monotonic() + RESPONSE_TIMEOUT
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ResponseTimeoutError(
                    f"Response timeout for slot={self._device.slot} feat_idx={feat_idx} fn={function}"
                )
            try:
                event = self._response_queue.get(timeout=remaining)
                if isinstance(event, HidppErrorEvent):
                    log.debug("HID++ error for slot=%d: 0x%02X", self._device.slot, event.error_code)
                    return None
                if (
                    isinstance(event, HidppResponseEvent)
                    and event.feature_index == feat_idx
                    and event.function == function
                ):
                    return event
            except queue.Empty:
                raise ResponseTimeoutError(
                    f"Response timeout for slot={self._device.slot} feat_idx={feat_idx} fn={function}"
                )
