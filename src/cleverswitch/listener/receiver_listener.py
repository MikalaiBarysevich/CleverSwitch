import logging
import queue

from ..event.write_event import WriteEvent
from ..listener.event_listener import EventListener
from ..parser.parser import parse
from ..topic.topic import Topic

log = logging.getLogger(__name__)

class ReceiverListener(EventListener):

    def run(self):
        self._topics["write_topic"].publish(WriteEvent(
            slot=-1,
            pid=self._device_info.pid,
            hid_message=bytes([0x10, 0xFF, 0x80, 0x02, 0x02, 0x00, 0x00]),
        ))
        super().run()
