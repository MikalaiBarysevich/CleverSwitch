import os
from pathlib import Path
from typing import IO


def try_lock(path: Path) -> IO | None:
    handle = open(path, "a+")
    try:
        _lock(handle)
    except OSError:
        handle.close()
        return None
    return handle


def _lock(handle: IO) -> None:
    if os.name == "nt":  # pragma: no cover
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
