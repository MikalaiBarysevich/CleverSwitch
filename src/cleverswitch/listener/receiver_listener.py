import queue

from ..event.device_connected_event import DeviceConnectedEvent
from ..event.diverted_host_change_event import DivertedHostChangeEvent
from ..event.host_change_event import HostChangeEvent
from ..parser.parser import parse

from ..listener.event_listener import EventListener
from ..publisher.publisher import Publisher


class ReceiverListener(EventListener):

    def __init__(self):
        self._event_queue = queue.Queue()
        super().__init__(daemon=True)

    def listen(self, raw_event: bytes) -> None:
        self._event_queue.put(raw_event)

    def run(self):
        # fire hid1.0+++ get connected devices to trigger connected events to add devices
        # 10 FF 80 02 02 00 00
        while True:
            raw_event = self._event_queue.get()
            parsed_event = parse(raw_event)

            if parsed_event is None:
                continue

            if isinstance(parsed_event, (HostChangeEvent, DivertedHostChangeEvent)):
                #publish to host change topic
                pass

            if isinstance(parsed_event, DeviceConnectedEvent):
                # register device it some dictionary
                # initiate data collection like feature indexes, type and name, if divertable
                pass
