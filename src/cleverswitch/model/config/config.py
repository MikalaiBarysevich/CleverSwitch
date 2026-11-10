import dataclasses
from pathlib import Path

from .args_settings import ArgsSettings
from .hooks_config import HooksConfig
from .logging_config import LoggingConfig


@dataclasses.dataclass(frozen=True)
class Config:
    hooks: HooksConfig
    arguments_settings: ArgsSettings
    cache_path: Path
    logging: LoggingConfig = dataclasses.field(default_factory=LoggingConfig)
