import dataclasses

from .hook_entry import HookEntry


@dataclasses.dataclass(frozen=True)
class HooksConfig:
    fire_for_all_devices: bool = False
    on_switch: tuple[HookEntry, ...] = ()
    on_connect: tuple[HookEntry, ...] = ()
    on_disconnect: tuple[HookEntry, ...] = ()
