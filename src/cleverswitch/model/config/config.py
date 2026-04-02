import dataclasses

from .args_settings import ArgsSettings
from .hooks_config import HooksConfig
from .settings import Settings


@dataclasses.dataclass(frozen=True)
class Config:
    hooks: HooksConfig
    settings: Settings
    arguments_settings: ArgsSettings
