import dataclasses

from .hook_type import HookType


@dataclasses.dataclass(frozen=True)
class HookEntry:
    name: str
    types: frozenset[HookType]
    path: str | None = None
    command: str | None = None
    timeout: int = 5
    fire_for_all_devices: bool | None = None  # None -> inherit HooksConfig global
