from ...event.write_event import WriteEvent
from ...hidpp.transport import HidDeviceInfo
from ...topic.topic import Topic
from .connection_triger import ConnectionTrigger

ENUMERATE_CONNECTED_DEVICES_MESSAGE = bytes([0x10, 0xFF, 0x80, 0x02, 0x02, 0x00, 0x00])


class ReceiverConnectionTrigger(ConnectionTrigger):
    def __init__(self, device_info: HidDeviceInfo, topics: dict[str, Topic]):
        super().__init__()
        self._topics = topics
        self._device_info = device_info

    def trigger(self):
        self._topics["write_topic"].publish(
            WriteEvent(
                slot=-1,
                pid=self._device_info.pid,
                hid_message=ENUMERATE_CONNECTED_DEVICES_MESSAGE,
            )
        )
