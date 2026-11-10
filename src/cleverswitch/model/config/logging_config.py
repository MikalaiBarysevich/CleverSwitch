import dataclasses
import logging
import os
from pathlib import Path

from ...log.log_paths import default_log_path
from ...util.util import get_system

DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 3


def _default_file_path() -> Path:
    return default_log_path(get_system(), os.environ, Path.home())


@dataclasses.dataclass(frozen=True)
class LoggingConfig:
    level: int = logging.INFO
    file_enabled: bool = True
    file_path: Path = dataclasses.field(default_factory=_default_file_path)
    max_bytes: int = DEFAULT_MAX_BYTES
    backup_count: int = DEFAULT_BACKUP_COUNT
