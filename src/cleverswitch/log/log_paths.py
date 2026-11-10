from collections.abc import Mapping
from pathlib import Path

from ..util.util import SYSTEM_MACOS, SYSTEM_WINDOWS

LOG_FILE_NAME = "cleverswitch.log"


def default_log_path(system: str, env: Mapping[str, str], home: Path) -> Path:
    if system == SYSTEM_MACOS:
        return home / "Library" / "Logs" / "CleverSwitch" / LOG_FILE_NAME
    if system == SYSTEM_WINDOWS:
        local = env.get("LOCALAPPDATA")
        base = Path(local) if local else home / "AppData" / "Local"
        return base / "CleverSwitch" / "Logs" / LOG_FILE_NAME
    state = env.get("XDG_STATE_HOME")
    base = Path(state) if state and Path(state).is_absolute() else home / ".local" / "state"
    return base / "cleverswitch" / LOG_FILE_NAME
