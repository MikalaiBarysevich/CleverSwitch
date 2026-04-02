import logging
import queue
from abc import ABC, abstractmethod
from threading import Thread

from ...event.hidpp_error_event import HidppErrorEvent
from ...event.hidpp_response_event import HidppResponseEvent
from ...event.write_event import WriteEvent
from ...hidpp.protocol import build_msg, pack_params
from ...model.logi_device import LogiDevice
from ...subscriber.subscriber import Subscriber
from ...topic.topic import Topic

log = logging.getLogger(__name__)

RESPONSE_TIMEOUT = 2.0


class InfoTask(ABC, Subscriber, Thread):
    """Base class for device info tasks that subscribe to event_topic and wait for HID++ responses."""

    def __init__(
        self,
        step_name: str,
        device: LogiDevice,
        topics: dict[str, Topic],
        request_id: int,
        sw_id: int,
    ) -> None:
        super().__init__(daemon=True)
        self._step_name = step_name
        self._device = device
        self._topics = topics
        self._response_queue: queue.Queue = queue.Queue()
        self._sw_id = sw_id
        self._request_id = (request_id & 0xFFF0) | self._sw_id
        topics["event_topic"].subscribe(self)

    def notify(self, event) -> None:
        if isinstance(event, HidppErrorEvent) and event.slot == self._device.slot:
            self._response_queue.put(event)
            return
        if (
            isinstance(event, HidppResponseEvent)
            and event.slot == self._device.slot
            and event.pid == self._device.pid
            and event.sw_id == self._sw_id
        ):
            self._response_queue.put(event)

    def run(self) -> None:
        if self._step_name not in self._device.pending_steps:
            log.info(f"Task {self._step_name} is already complete")
        else:
            self.doTask()

        if len(self._device.pending_steps) == 0:
            # todo(CLEV-51): must publish to another subscriber to track if all tasks completed
            log.info(f"REMOVE ME LATER device setup completed device={self._device}")
        else:
            self._fire_dependent_steps()

    @abstractmethod
    def doTask(self) -> None: ...

    def _send_request(self, *params, request_id: int | None = None) -> None:
        params_bytes = pack_params(params)
        rid = ((request_id & 0xFFF0) | self._sw_id) if request_id is not None else self._request_id
        msg = build_msg(self._device.slot, rid, params_bytes)
        self._topics["write_topic"].publish(WriteEvent(slot=self._device.slot, pid=self._device.pid, hid_message=msg))

    def _wait_response(self, timeout: float = RESPONSE_TIMEOUT) -> HidppResponseEvent | HidppErrorEvent | None:
        try:
            return self._response_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _fire_dependent_steps(self):
        log.debug(f"No dependent steps for {self._step_name}")
