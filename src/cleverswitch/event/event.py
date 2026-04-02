import dataclasses


@dataclasses.dataclass
class Event:
    slot: int
    pid: int  # receiver pid or bt device wpid
