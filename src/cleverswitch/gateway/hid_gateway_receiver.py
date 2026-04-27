from ..connection.trigger.connection_triger import ConnectionTrigger
from ..event.transport_disconnected_event import TransportDisconnectedEvent
from ..gateway.hid_gateway import HidGateway
from ..hidpp.transport import HidDeviceInfo
from ..listener.event_listener import EventListener
from ..topic.topics import Topics


class HidGatewayReceiver(HidGateway):
    """HidGateway subclass for Bolt/Unifying USB receivers.

    Extends state-change behavior so that:
    - On connect (or reconnect after USB re-plug): fires the connection trigger
      to re-arm HID++ notifications and re-enumerate paired devices.
    - On disconnect: publishes TransportDisconnectedEvent so the fan-out
      subscriber can mark all paired devices as offline.

    The base class remains generic with no event-publishing side effects,
    keeping BT and receiver paths symmetric.
    """

    def __init__(
        self,
        device_info: HidDeviceInfo,
        event_listener: EventListener,
        topics: Topics,
        connection_trigger: ConnectionTrigger,
    ) -> None:
        super().__init__(device_info, event_listener)
        self._topics = topics
        self._connection_trigger = connection_trigger

    def _set_connected(self, state: bool) -> None:
        super()._set_connected(state)
        if state:
            self._connection_trigger.trigger()
        else:
            self._topics.hid_event.publish(TransportDisconnectedEvent(slot=0, pid=self._device_info.pid))
