import dataclasses

from .args_settings import ArgsSettings
from .hooks_config import HooksConfig


@dataclasses.dataclass(frozen=True)
class Config:
    hooks: HooksConfig
    arguments_settings: ArgsSettings
