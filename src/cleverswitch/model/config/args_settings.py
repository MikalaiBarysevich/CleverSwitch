import dataclasses


@dataclasses.dataclass(frozen=True)
class ArgsSettings:
    verbose_extra: bool = False
