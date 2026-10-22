import logging
import queue
from threading import Thread

from ..event.event import Event
from ..hidpp.transport import HidDeviceInfo
from ..parser.parser import parse
from ..topic.topics import Topics

log = logging.getLogger(__name__)


class EventListener(Thread):
    def __init__(self, device_info: HidDeviceInfo, topics: Topics):
        self._device_info = device_info
        self._event_queue = queue.Queue()
        self._topics = topics
        super().__init__(daemon=True)

    def listen(self, raw_event: bytes) -> None:
        self._event_queue.put(raw_event)

    # Typed events share the raw-report queue so they stay in order with this device's reports.
    def emit(self, event: Event) -> None:
        self._event_queue.put(event)

    def run(self):
        while True:
            item = self._event_queue.get()
            # One malformed report must not kill this thread — it is the only path from HID to
            # the topics, so its death makes the whole process deaf. Mirrors Topic._notify.
            try:
                parsed_event = item if isinstance(item, Event) else parse(self._device_info.pid, item)
                if parsed_event is None:
                    continue

                log.debug(f"Parsed event: {parsed_event}")
                self._topics.hid_event.publish(parsed_event)
            except Exception:
                log.exception(f"Failed to handle HID event from pid=0x{self._device_info.pid:04X}")
