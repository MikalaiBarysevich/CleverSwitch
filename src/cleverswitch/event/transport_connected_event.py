import dataclasses

from ..event.event import Event


@dataclasses.dataclass
class TransportConnectedEvent(Event):
    """Fired by DeviceLink when a receiver or Bluetooth device becomes present. `slot` is unused (0)."""

    connection_type: str  # CONNECTION_RECEIVER or CONNECTION_BLUETOOTH, as in HidDeviceInfo
