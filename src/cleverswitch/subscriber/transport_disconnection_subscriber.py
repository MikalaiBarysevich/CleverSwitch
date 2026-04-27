import logging

from ..event.device_connected_event import DeviceConnectedEvent
from ..event.transport_disconnected_event import TransportDisconnectedEvent
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..topic.topics import Topics

log = logging.getLogger(__name__)


class TransportDisconnectionSubscriber(Subscriber):
    """Fans out a TransportDisconnectedEvent into one DeviceConnectedEvent(link_established=False)
    per registered device whose pid matches the dropped transport.

    This decouples gateway transport-state from per-device disconnect logic:
    the gateway knows only which pid disconnected; this subscriber translates
    that into per-device events so that DeviceConnectionSubscriber and
    EventHookSubscriber react as if each device sent a normal disconnect report.
    """

    def __init__(self, device_registry: LogiDeviceRegistry, topics: Topics) -> None:
        self._device_registry = device_registry
        self._topics = topics
        topics.hid_event.subscribe(self)

    def notify(self, event) -> None:
        if not isinstance(event, TransportDisconnectedEvent):
            return

        devices = self._device_registry.all_entries()
        for device in devices:
            if device.pid != event.pid:
                continue
            log.debug(
                f"Transport disconnected pid=0x{event.pid:04X}: marking device wpid=0x{device.wpid:04X} disconnected"
            )
            self._topics.hid_event.publish(
                DeviceConnectedEvent(
                    slot=device.slot,
                    pid=device.pid,
                    wpid=device.wpid,
                    link_established=False,
                    device_type=None,
                )
            )
