import dataclasses

from .hook_entry import HookEntry


@dataclasses.dataclass(frozen=True)
class HooksConfig:
    on_switch: tuple[HookEntry, ...] = ()
    on_connect: tuple[HookEntry, ...] = ()
    on_disconnect: tuple[HookEntry, ...] = ()
