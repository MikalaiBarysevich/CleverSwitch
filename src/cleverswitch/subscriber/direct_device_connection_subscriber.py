from ..event.device_connected_event import DeviceConnectedEvent
from ..event.transport_connected_event import TransportConnectedEvent
from ..subscriber.subscriber import Subscriber
from ..topic.topics import Topics

# A directly connected (Bluetooth) device has no receiver slot.
DIRECT_DEVICE_SLOT = 0xFF


class DirectDeviceConnectionSubscriber(Subscriber):
    """Turns a Bluetooth transport coming up into a DeviceConnectedEvent for that device.

    A Bluetooth HID collection is a single device, so its transport connecting is the device
    connecting; its pid doubles as the wpid. The disconnect side needs no counterpart:
    TransportDisconnectionSubscriber already fans out by pid.
    """

    def __init__(self, topics: Topics) -> None:
        self._topics = topics
        topics.hid_event.subscribe(self)

    def notify(self, event) -> None:
        if not isinstance(event, TransportConnectedEvent) or event.connection_type != "bluetooth":
            return
        self._topics.hid_event.publish(
            DeviceConnectedEvent(
                slot=DIRECT_DEVICE_SLOT,
                pid=event.pid,
                wpid=event.pid,
                link_established=True,
                device_type=None,
            )
        )
