import dataclasses

from ..event.event import Event


@dataclasses.dataclass
class TransportConnectedEvent(Event):
    """Fired by a gateway when its HID transport comes up. `slot` is unused (0)."""

    connection_type: str  # "receiver" or "bluetooth", as in HidDeviceInfo
