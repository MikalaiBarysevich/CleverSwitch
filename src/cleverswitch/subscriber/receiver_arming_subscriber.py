from ..event.transport_connected_event import TransportConnectedEvent
from ..event.write_event import WriteEvent
from ..subscriber.subscriber import Subscriber
from ..topic.topics import Topics

ENABLE_HIDPP_NOTIFICATIONS_MESSAGE = bytes([0x10, 0xFF, 0x80, 0x00, 0x00, 0x09, 0x00])
ENUMERATE_CONNECTED_DEVICES_MESSAGE = bytes([0x10, 0xFF, 0x80, 0x02, 0x02, 0x00, 0x00])


class ReceiverArmingSubscriber(Subscriber):
    """On every receiver (re)connect, enables HID++ notifications and enumerates paired devices.

    The receiver's notification register is RAM-only and resets at USB power-up, so it must be
    re-armed after each re-plug before the enumeration can produce 0x41 connection notifications.
    """

    def __init__(self, topics: Topics) -> None:
        self._topics = topics
        topics.hid_event.subscribe(self)

    def notify(self, event) -> None:
        if not isinstance(event, TransportConnectedEvent) or event.connection_type != "receiver":
            return
        for message in (ENABLE_HIDPP_NOTIFICATIONS_MESSAGE, ENUMERATE_CONNECTED_DEVICES_MESSAGE):
            self._topics.write.publish(WriteEvent(slot=-1, pid=event.pid, hid_message=message))
