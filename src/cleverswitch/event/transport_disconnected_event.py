import dataclasses

from ..event.event import Event


@dataclasses.dataclass
class TransportDisconnectedEvent(Event):
    """Fired by DeviceLink when a receiver or Bluetooth device stops being present.

    `slot` is unused for transport-level events; callers should set it to 0.
    `pid` identifies the HID product whose transport dropped.
    """
