import dataclasses


@dataclasses.dataclass
class LogiDevice:
    wpid: int
    pid: int
    slot: int  # 1-6 for receiver-paired, 0xFF for Bluetooth direct
    role: str | None  # "keyboard" or "mouse"
    available_features: dict[int, int]  # feature_code → feature_index
    name: str | None = None
    divertable_cids: set[int] = dataclasses.field(default_factory=set)
    info_step: int = 0
