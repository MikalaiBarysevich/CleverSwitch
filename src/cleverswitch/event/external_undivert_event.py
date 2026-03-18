import dataclasses

from ..event.event import Event


@dataclasses.dataclass
class ExternalUndivertEvent(Event):
    target_host_cid: int
