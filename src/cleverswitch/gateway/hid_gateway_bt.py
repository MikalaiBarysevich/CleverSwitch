from ..event.transport_connected_event import TransportConnectedEvent
from ..event.transport_disconnected_event import TransportDisconnectedEvent
from ..gateway.hid_gateway import HidGateway


class HidGatewayBT(HidGateway):
    def _do_write(self, transport, msg: bytes) -> None:
        transport.write_output_report(msg)

    def _set_connected(self, state: bool) -> None:
        super()._set_connected(state)
        self._emit_state(state)

    # The state is passed in rather than read from _connected, which another thread may have
    # changed by the time the event is built.
    def _emit_state(self, state: bool) -> None:
        pid = self._device_info.pid
        if state:
            self._event_listener.emit(TransportConnectedEvent(slot=0, pid=pid, connection_type="bluetooth"))
        else:
            self._event_listener.emit(TransportDisconnectedEvent(slot=0, pid=pid))
