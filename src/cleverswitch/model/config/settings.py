import dataclasses


@dataclasses.dataclass(frozen=True)
class Settings:
    read_timeout_ms: int = 2000
