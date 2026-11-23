from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Callable, Mapping

from ...errors.errors import EdgeSwitchError
from ..edge_sink import EdgeSink
from ..geometry import EDGE_TOLERANCE_PX
from .edge_bus import BUS_NAME, INTERFACE, OBJECT_PATH, EdgeBus

log = logging.getLogger(__name__)

KWIN = "org.kde.KWin"
SCRIPTING_PATH = "/Scripting"
SCRIPTING_INTERFACE = "org.kde.kwin.Scripting"
SCRIPT_INTERFACE = "org.kde.kwin.Script"
PLUGIN = "cleverswitch-edge"

# Runs inside KWin on every cursor move, but calls CleverSwitch only when the set of outer edges under the
# cursor changes. Same rule as geometry.edges_at: right and bottom are exclusive.
KWIN_SCRIPT = f"""\
const NAME = "{BUS_NAME}", PATH = "{OBJECT_PATH}", IFACE = "{INTERFACE}";
const TOLERANCE = {EDGE_TOLERANCE_PX:g};
let last = -1;
function edgesAt(p, g) {{
    let mask = 0;
    if (p.x <= g.x + TOLERANCE) mask |= 1;
    if (p.x >= g.x + g.width - 1 - TOLERANCE) mask |= 2;
    if (p.y <= g.y + TOLERANCE) mask |= 4;
    if (p.y >= g.y + g.height - 1 - TOLERANCE) mask |= 8;
    return mask;
}}
function update() {{
    const mask = edgesAt(workspace.cursorPos, workspace.virtualScreenGeometry);
    if (mask !== last) {{
        last = mask;
        callDBus(NAME, PATH, IFACE, "Edges", mask);
    }}
}}
workspace.cursorPosChanged.connect(update);
workspace.virtualScreenGeometryChanged.connect(update);
update();
"""


# A fixed private path: a daemon killed mid-run leaves no stray file behind, and the next start overwrites it.
def script_path(env: Mapping[str, str] = os.environ) -> str:
    runtime = env.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    return os.path.join(runtime, "cleverswitch", "kwin-edge.js")


def write_script(path: str | None = None) -> str:
    target = path or script_path()
    os.makedirs(os.path.dirname(target), mode=0o700, exist_ok=True)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(KWIN_SCRIPT)
    return target


class KWinCursor:
    """The KDE cursor feed for LibinputLoop: a KWin script, loaded while CleverSwitch runs, reports the outer
    edges under the cursor over the session bus. KWin scripts cannot see modifiers, so keys still come from
    libinput. A script left behind by a killed daemon is unloaded before loading ours."""

    name = "KWin"

    def __init__(self, edge_bus: EdgeBus, script_writer: Callable[[], str] = write_script):
        self._edge_bus = edge_bus
        self._path: str | None = None
        self._loaded = False
        self._closed = False
        try:
            self._path = script_writer()
            self._scripting("unloadScript", "s", PLUGIN)
            script_id = int(self._scripting("loadScript", "ss", self._path, PLUGIN)[0])
            if script_id < 0:
                raise EdgeSwitchError("KWin refused the edge-switch script")
            self._loaded = True
            try:
                edge_bus.bus.call(KWIN, f"{SCRIPTING_PATH}/Script{script_id}", SCRIPT_INTERFACE, "run")
            except OSError as e:
                raise EdgeSwitchError(f"cannot run the KWin script; edge switch needs KDE Plasma 6 ({e})") from e
        except BaseException:
            self.close()
            raise

    def fd(self) -> int:
        return self._edge_bus.fd()

    # KWin leaving the bus ends the loop by itself; there is nothing to probe.
    def health_check(self) -> bool:
        return True

    def drain(self, sink: EdgeSink) -> None:
        self._edge_bus.drain(sink)

    def on_motion(self, _sink: EdgeSink) -> None:
        pass

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self._loaded:
                try:
                    self._scripting("unloadScript", "s", PLUGIN)
                except OSError as e:
                    log.debug(f"Cannot unload the KWin script: {e}")
        finally:
            # The temp script must not outlive the loop even when unloading or closing the bus fails.
            try:
                self._edge_bus.close()
            finally:
                if self._path is not None:
                    try:
                        os.unlink(self._path)
                    except OSError:
                        pass

    def _scripting(self, member: str, signature: str, *body) -> tuple:
        return self._edge_bus.bus.call(KWIN, SCRIPTING_PATH, SCRIPTING_INTERFACE, member, signature, body)
