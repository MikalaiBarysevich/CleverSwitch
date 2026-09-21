import dataclasses
from pathlib import Path

from .args_settings import ArgsSettings
from .easy_switch_config import EasySwitchConfig
from .hooks_config import HooksConfig


@dataclasses.dataclass(frozen=True)
class Config:
    hooks: HooksConfig
    arguments_settings: ArgsSettings
    cache_path: Path
    easy_switch: EasySwitchConfig
