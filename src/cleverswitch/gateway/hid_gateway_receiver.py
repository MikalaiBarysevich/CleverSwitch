from ..event.transport_connected_event import TransportConnectedEvent
from ..event.transport_disconnected_event import TransportDisconnectedEvent
from ..gateway.hid_gateway import HidGateway


class HidGatewayReceiver(HidGateway):
    """HidGateway subclass for Bolt/Unifying USB receivers.

    Emits typed transport lifecycle events through its EventListener:
    - On connect (or reconnect after USB re-plug): TransportConnectedEvent, which
      ReceiverArmingSubscriber turns into the enable-notifications + enumerate writes.
    - On disconnect: TransportDisconnectedEvent, which TransportDisconnectionSubscriber
      fans out to every paired device.
    """

    def _set_connected(self, state: bool) -> None:
        super()._set_connected(state)
        pid = self._device_info.pid
        if state:
            self._event_listener.emit(TransportConnectedEvent(slot=0, pid=pid, connection_type="receiver"))
        else:
            self._event_listener.emit(TransportDisconnectedEvent(slot=0, pid=pid))
