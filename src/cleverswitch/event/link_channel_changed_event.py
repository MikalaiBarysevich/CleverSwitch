import dataclasses

from ..event.event import Event

CHANNEL_GATT = "gatt"


@dataclasses.dataclass
class LinkChannelChangedEvent(Event):
    """A secondary channel of a still-present device came up or went down. `slot` is unused (0)."""

    channel: str  # CHANNEL_GATT
    up: bool
