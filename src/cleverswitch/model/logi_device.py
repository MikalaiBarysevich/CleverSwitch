import dataclasses


@dataclasses.dataclass
class LogiDevice:
    wpid: int
    pid: int
    slot: int  # 1-6 for receiver-paired, 0xFF for Bluetooth direct
    role: str | None  # "keyboard" or "mouse"
    available_features: dict[int, int]  # feature_code → feature_index
    name: str | None = None
    supported_flags: set[int] = dataclasses.field(default_factory=set)
    pending_steps: set[str] = dataclasses.field(
        default_factory=lambda: {
            "resolve_reprog",
            "resolve_change_host",
            "resolve_x0005",
            "find_es_cids_flags",
            "get_device_type",
            "get_device_name",
        }
    )
    connected: bool = True

    def __str__(self):
        return f"'{self.name}': pid={hex(self.pid)}, wpid={hex(self.wpid)}, slot={self.slot}"
