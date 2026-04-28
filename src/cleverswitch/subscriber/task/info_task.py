import logging
import queue
from abc import ABC, abstractmethod
from threading import Thread

from ...event.hidpp_error_event import HidppErrorEvent
from ...event.hidpp_response_event import HidppResponseEvent
from ...event.info_task_progress_event import InfoTaskProgressEvent
from ...event.write_event import WriteEvent
from ...hidpp.protocol import build_msg, pack_params
from ...model.logi_device import LogiDevice
from ...subscriber.subscriber import Subscriber
from ...topic.topics import Topics

log = logging.getLogger(__name__)

RESPONSE_TIMEOUT = 2.0


class InfoTask(ABC, Subscriber, Thread):
    """Base class for device info tasks that subscribe to hid_event and wait for HID++ responses."""

    def __init__(
        self,
        step_name: str,
        device: LogiDevice,
        topics: Topics,
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
        topics.hid_event.subscribe(self)

    def notify(self, event) -> None:
        if (
            isinstance(event, (HidppResponseEvent, HidppErrorEvent))
            and event.slot == self._device.slot
            and event.pid == self._device.pid
            and event.sw_id == self._sw_id
        ):
            self._response_queue.put(event)

    def run(self) -> None:
        already_done = self._step_name not in self._device.pending_steps
        if not already_done:
            try:
                self.doTask()
            except Exception:
                log.exception(f"Unhandled error in task {self._step_name} for wpid=0x{self._device.wpid:04X}")
        success = already_done or self._step_name not in self._device.pending_steps
        if success:
            self._device.connected = True
            self._fire_dependent_steps()
        self._topics.info_progress.publish(
            InfoTaskProgressEvent(
                slot=self._device.slot,
                pid=self._device.pid,
                step_name=self._step_name,
                success=success,
                device=self._device,
            )
        )

    @abstractmethod
    def doTask(self) -> None: ...

    def _send_request(self, *params, request_id: int | None = None) -> None:
        params_bytes = pack_params(params)
        rid = ((request_id & 0xFFF0) | self._sw_id) if request_id is not None else self._request_id
        msg = build_msg(self._device.slot, rid, params_bytes)
        self._topics.write.publish(WriteEvent(slot=self._device.slot, pid=self._device.pid, hid_message=msg))

    def _wait_response(self, timeout: float = RESPONSE_TIMEOUT) -> HidppResponseEvent | HidppErrorEvent | None:
        try:
            return self._response_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _fire_dependent_steps(self):
        log.debug(f"No dependent steps for {self._step_name}")
