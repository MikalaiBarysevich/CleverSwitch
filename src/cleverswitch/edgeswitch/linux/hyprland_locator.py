from __future__ import annotations

import json
import logging
import os
import socket
from collections.abc import Callable, Mapping

from ..edge_sink import EdgeSink, Location
from ..geometry import Rect, union

log = logging.getLogger(__name__)

SOCKET_NAME = ".socket.sock"
TIMEOUT_S = 0.25
MAX_REPLY = 1 << 20

Request = Callable[[str, bytes], bytes]


# Hyprland serves its command socket synchronously and freezes on a connection left open, so every request
# connects, asks, reads to EOF and closes.
def request(path: str, command: bytes, timeout: float = TIMEOUT_S) -> bytes:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout)
        sock.connect(path)
        sock.sendall(command)
        chunks = []
        size = 0
        while chunk := sock.recv(65536):
            size += len(chunk)
            if size > MAX_REPLY:
                raise ValueError(f"Hyprland reply over {MAX_REPLY} bytes")
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        sock.close()


def parse_cursor(reply: bytes) -> tuple[float, float]:
    data = json.loads(reply)
    return float(data["x"]), float(data["y"])


# The union of the active monitors in logical coordinates, the space the cursor position is reported in.
def parse_bounds(reply: bytes) -> Rect | None:
    rects = []
    for monitor in json.loads(reply):
        if monitor.get("disabled") or monitor.get("mirrorOf", "none") != "none":
            continue
        width, height = float(monitor["width"]), float(monitor["height"])
        if int(monitor.get("transform", 0)) % 2 == 1:  # rotated 90 or 270 degrees
            width, height = height, width
        scale = float(monitor.get("scale", 1.0)) or 1.0
        x, y = float(monitor["x"]), float(monitor["y"])
        rects.append(Rect(x, y, x + width / scale, y + height / scale))
    return union(rects)


# The instance named in the environment first, then every instance's socket, newest first: a systemd user
# unit often lacks HYPRLAND_INSTANCE_SIGNATURE, and a restarted Hyprland gets a new one.
def socket_candidates(
    env: Mapping[str, str],
    listdir: Callable[[str], list[str]] = os.listdir,
    mtime: Callable[[str], float] = os.path.getmtime,
) -> list[str]:
    runtime = env.get("XDG_RUNTIME_DIR")
    if not runtime:
        return []
    base = os.path.join(runtime, "hypr")
    candidates = []
    signature = env.get("HYPRLAND_INSTANCE_SIGNATURE")
    if signature:
        candidates.append(os.path.join(base, signature, SOCKET_NAME))
    try:
        found = [os.path.join(base, name, SOCKET_NAME) for name in listdir(base)]
    except OSError:
        found = []
    found.sort(key=lambda path: _safe_mtime(mtime, path), reverse=True)
    candidates.extend(path for path in found if path not in candidates)
    return candidates


def _safe_mtime(mtime: Callable[[str], float], path: str) -> float:
    try:
        return mtime(path)
    except OSError:
        return 0.0


class HyprlandLocator:
    """Where the cursor is, asked from Hyprland's IPC socket: the Linux counterpart of GetCursorPos.
    Both queries are made per burst, so a monitor added, rotated or rescaled mid-hold is seen at once; each
    costs about 0.03 ms. locate() raises OSError once Hyprland stops answering, which ends the loop until the
    next revive."""

    name = "Hyprland"

    def __init__(self, path_candidates: Callable[[], list[str]], request: Request = request):
        self._path_candidates = path_candidates
        self._request = request
        self._path: str | None = None

    @classmethod
    def detect(
        cls,
        env: Mapping[str, str] = os.environ,
        listdir: Callable[[str], list[str]] = os.listdir,
    ) -> HyprlandLocator | None:
        if not socket_candidates(env, listdir, lambda _path: 0.0):
            return None
        return cls(lambda: socket_candidates(env, listdir))

    def probe(self) -> bool:
        for path in self._path_candidates():
            try:
                parse_cursor(self._request(path, b"j/cursorpos"))
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if self._path != path:
                log.debug(f"Edge switch reads the cursor through {path}")
            self._path = path
            return True
        return False

    def fd(self) -> None:
        return None

    # Hyprland may have restarted on a new socket while this loop sat idle; probe re-resolves the candidates.
    def health_check(self) -> bool:
        return self.probe()

    def drain(self, _sink: EdgeSink) -> None:
        pass

    def on_motion(self, sink: EdgeSink) -> None:
        sink.on_motion(self.locate)

    def close(self) -> None:
        pass

    def locate(self) -> Location:
        if self._path is None:
            raise OSError("Hyprland was not probed")
        try:
            bounds = parse_bounds(self._request(self._path, b"j/monitors"))
            x, y = parse_cursor(self._request(self._path, b"j/cursorpos"))
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise OSError(f"Hyprland stopped answering ({e})") from e
        return x, y, bounds
