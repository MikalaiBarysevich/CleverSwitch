import dataclasses


@dataclasses.dataclass(frozen=True)
class HookEntry:
    path: str
    timeout: int = 5
