from ...event.write_event import WriteEvent
from ...hidpp.constants import (
    DEVICE_RECEIVER,
    GET_LONG_REGISTER_RSP,
    PAIRING_INFO_SUB_PAGE_BASE,
    REGISTER_PAIRING_INFO,
    REPORT_SHORT,
)
from ...hidpp.transport import HidDeviceInfo
from ...topic.topic import Topic
from .connection_triger import ConnectionTrigger

MAX_RECEIVER_SLOTS = 6


class ReceiverConnectionTriggerMac(ConnectionTrigger):
    def __init__(self, device_info: HidDeviceInfo, topics: dict[str, Topic]):
        super().__init__()
        self._topics = topics
        self._device_info = device_info

    def trigger(self):
        for slot in range(1, MAX_RECEIVER_SLOTS + 1):
            sub_page = PAIRING_INFO_SUB_PAGE_BASE + (slot - 1)
            message = bytes(
                [REPORT_SHORT, DEVICE_RECEIVER, GET_LONG_REGISTER_RSP, REGISTER_PAIRING_INFO, sub_page, 0x00, 0x00]
            )
            self._topics["write_topic"].publish(
                WriteEvent(
                    slot=-1,
                    pid=self._device_info.pid,
                    hid_message=message,
                )
            )
