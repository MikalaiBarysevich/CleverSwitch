import dataclasses

from ..event.event import Event


@dataclasses.dataclass
class TransportDisconnectedEvent(Event):
    """Fired by HidGatewayReceiver when the USB receiver transport goes offline.

    `slot` is unused for transport-level events; callers should set it to 0.
    `pid` identifies the receiver whose transport dropped.
    """
