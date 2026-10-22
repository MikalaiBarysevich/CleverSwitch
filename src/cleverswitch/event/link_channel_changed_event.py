import dataclasses

from ..event.event import Event


@dataclasses.dataclass
class LinkChannelChangedEvent(Event):
    """A secondary channel of a still-present device came up or went down. `slot` is unused (0)."""

    channel: str  # "gatt"
    up: bool
