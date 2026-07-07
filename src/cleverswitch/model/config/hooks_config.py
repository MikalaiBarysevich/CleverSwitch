import dataclasses

from .hook_entry import HookEntry
from .hook_type import HookType


@dataclasses.dataclass(frozen=True)
class HooksConfig:
    fire_for_all_devices: bool = False
    hooks: dict[str, HookEntry] = dataclasses.field(default_factory=dict)

    def for_type(self, hook_type: HookType) -> tuple[HookEntry, ...]:
        return tuple(h for h in self.hooks.values() if hook_type in h.types)
