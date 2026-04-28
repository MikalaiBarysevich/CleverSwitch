from ...event.write_event import WriteEvent
from ...hidpp.transport import HidDeviceInfo
from ...topic.topics import Topics
from .connection_triger import ConnectionTrigger

ENABLE_HIDPP_NOTIFICATIONS_MESSAGE = bytes([0x10, 0xFF, 0x80, 0x00, 0x00, 0x09, 0x00])
ENUMERATE_CONNECTED_DEVICES_MESSAGE = bytes([0x10, 0xFF, 0x80, 0x02, 0x02, 0x00, 0x00])


class ReceiverConnectionTrigger(ConnectionTrigger):
    def __init__(self, device_info: HidDeviceInfo, topics: Topics):
        super().__init__()
        self._topics = topics
        self._device_info = device_info

    def trigger(self):
        self._topics.write.publish(
            WriteEvent(
                slot=-1,
                pid=self._device_info.pid,
                hid_message=ENABLE_HIDPP_NOTIFICATIONS_MESSAGE,
            )
        )
        self._topics.write.publish(
            WriteEvent(
                slot=-1,
                pid=self._device_info.pid,
                hid_message=ENUMERATE_CONNECTED_DEVICES_MESSAGE,
            )
        )
