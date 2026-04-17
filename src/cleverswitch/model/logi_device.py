import dataclasses

from ..subscriber.task.constants import Task


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
            Task.Feature.Name.CID_REPORTING,
            Task.Feature.Name.CHANGE_HOST,
            Task.Feature.Name.NAME_AND_TYPE,
            Task.Name.FIND_ES_CIDS_FLAGS,
            Task.Name.GET_DEVICE_TYPE,
            Task.Name.GET_DEVICE_NAME,
        }
    )
    connected: bool = True

    def __str__(self):
        transport = "BT" if self.slot == 0xFF else "receiver"
        return f"'{self.name}': transport={transport}, pid={hex(self.pid)}, wpid={hex(self.wpid)}"
