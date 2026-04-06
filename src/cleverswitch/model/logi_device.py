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
    persistently_divertable_cids: set[int] = dataclasses.field(default_factory=set)
    pending_steps: set[str] = dataclasses.field(
        default_factory=lambda: {
            "resolve_reprog",
            "resolve_change_host",
            "resolve_x0005",
            "find_divertable_cids",
            "get_device_type",
            "get_device_name",
        }
    )
    connected: bool = True
