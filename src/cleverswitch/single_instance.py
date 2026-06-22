"""Single-instance guard.

Prevents two CleverSwitch daemons from running at once and contending over the
shared Logitech receiver, which corrupts HID++ traffic.
"""

from __future__ import annotations

import logging
from pathlib import Path

from filelock import FileLock, Timeout

from .errors.errors import AlreadyRunningError

log = logging.getLogger(__name__)

_DEFAULT_LOCK_PATH = Path("~/.config/cleverswitch/cleverswitch.lock").expanduser()


def acquire_single_instance_lock(lock_path: Path | None = None) -> FileLock:
    path = lock_path if lock_path is not None else _DEFAULT_LOCK_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(path))
    try:
        lock.acquire(timeout=0)
    except Timeout as e:
        raise AlreadyRunningError(f"Another CleverSwitch instance already holds {path}") from e
    return lock
