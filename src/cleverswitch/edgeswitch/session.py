from __future__ import annotations

import glob
import os
from collections.abc import Callable, Mapping
from enum import StrEnum


class LinuxSession(StrEnum):
    X11 = "x11"
    WAYLAND = "wayland"
    UNKNOWN = "unknown"


# A systemd user unit often starts without DISPLAY or WAYLAND_DISPLAY, so a Wayland socket in the
# runtime dir is the last hint. UNKNOWN goes to evdev, which does not depend on the session at all.
def detect_linux_session(env: Mapping[str, str], find_sockets: Callable[[str], list[str]] = glob.glob) -> LinuxSession:
    if env.get("WAYLAND_DISPLAY") or env.get("XDG_SESSION_TYPE", "").lower() == "wayland":
        return LinuxSession.WAYLAND
    if env.get("DISPLAY"):
        return LinuxSession.X11
    runtime_dir = env.get("XDG_RUNTIME_DIR")
    if runtime_dir and find_sockets(os.path.join(runtime_dir, "wayland-*")):
        return LinuxSession.WAYLAND
    return LinuxSession.UNKNOWN
