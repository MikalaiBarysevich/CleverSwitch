import dataclasses

from ..event.event import Event
from ..hidpp.constants import HOST_SWITCH_CIDS


@dataclasses.dataclass
class SetReportFlagEvent(Event):
    wpid: int
    cids: set[int] = dataclasses.field(default_factory=lambda: set(HOST_SWITCH_CIDS))
    enable: bool = True
