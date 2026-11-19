import os
from unittest.mock import MagicMock

import pytest

from cleverswitch.edgeswitch.geometry import EDGE_TOLERANCE_PX
from cleverswitch.edgeswitch.linux import kwin
from cleverswitch.edgeswitch.linux.edge_bus import BUS_NAME, INTERFACE, OBJECT_PATH, EdgeBus
from cleverswitch.edgeswitch.linux.kwin import KWIN, KWIN_SCRIPT, PLUGIN, KWinCursor, write_script
from cleverswitch.errors.errors import EdgeSwitchError
from cleverswitch.model.config.edge import Edge

from .fake_bus import PEER_OWNER, FakeBus, call

SCRIPT_PATH = "/tmp/cleverswitch-kwin-test.js"


def _bus(script_id=7, run_error=None, unload_error=None):
    results = {(KWIN, "loadScript"): (script_id,)}
    if run_error is not None:
        results[(KWIN, "run")] = run_error
    bus = FakeBus(owners={KWIN: PEER_OWNER}, results=results)
    if unload_error is not None:
        real_call = bus.call

        def call_with_failing_unload(destination, path, interface, member, signature="", body=()):
            if member == "unloadScript" and bus.member_calls("loadScript"):
                bus.calls.append((destination, path, interface, member, tuple(body)))
                raise unload_error
            return real_call(destination, path, interface, member, signature, body)

        bus.call = call_with_failing_unload
    return bus


def _cursor(bus, writer=lambda: SCRIPT_PATH):
    return KWinCursor(EdgeBus(bus, KWIN), writer)


def test_script_carries_the_bus_constants_and_the_tolerance():
    for constant in (BUS_NAME, OBJECT_PATH, INTERFACE):
        assert f'"{constant}"' in KWIN_SCRIPT
    assert f"TOLERANCE = {EDGE_TOLERANCE_PX:g};" in KWIN_SCRIPT
    assert '"Edges"' in KWIN_SCRIPT


def test_write_script_creates_a_private_file(tmp_path):
    path = write_script(str(tmp_path / "kwin-edge.js"))
    assert open(path).read() == KWIN_SCRIPT
    assert os.stat(path).st_mode & 0o777 == 0o600


def test_start_unloads_a_leftover_then_loads_and_runs():
    bus = _bus()
    _cursor(bus)
    kwin_calls = [(c[1], c[3], c[4]) for c in bus.calls if c[0] == KWIN]
    assert kwin_calls == [
        ("/Scripting", "unloadScript", (PLUGIN,)),
        ("/Scripting", "loadScript", (SCRIPT_PATH, PLUGIN)),
        ("/Scripting/Script7", "run", ()),
    ]


def test_a_refused_script_closes_everything(tmp_path):
    bus = _bus(script_id=-1)
    path = tmp_path / "s.js"
    path.write_text("x")
    with pytest.raises(EdgeSwitchError, match="refused"):
        _cursor(bus, lambda: str(path))
    assert bus.closed
    assert not path.exists()
    assert len(bus.member_calls("unloadScript")) == 1  # nothing of ours was loaded


def test_plasma_5_cannot_run_the_script():
    bus = _bus(run_error=OSError("UnknownObject"))
    with pytest.raises(EdgeSwitchError, match="Plasma 6"):
        _cursor(bus)
    assert len(bus.member_calls("unloadScript")) == 2
    assert bus.closed


def test_edges_from_kwin_reach_the_sink():
    bus = _bus()
    cursor = _cursor(bus)
    sink = MagicMock()
    bus.push(call("Edges", 2))
    cursor.drain(sink)
    sink.on_edges.assert_called_once_with(frozenset({Edge.RIGHT}))
    assert cursor.fd() == bus.fd()
    cursor.on_motion(sink)
    assert cursor.health_check()
    sink.on_motion.assert_not_called()


def test_close_unloads_closes_and_removes_once(tmp_path):
    bus = _bus()
    path = tmp_path / "s.js"
    path.write_text("x")
    cursor = _cursor(bus, lambda: str(path))
    cursor.close()
    cursor.close()
    assert len(bus.member_calls("unloadScript")) == 2
    assert bus.closed
    assert not path.exists()


def test_close_survives_a_failed_unload_and_a_missing_file():
    bus = _bus(unload_error=OSError("KWin gone"))
    cursor = _cursor(bus, lambda: "/nonexistent/cleverswitch.js")
    cursor.close()
    assert bus.closed


def test_name_is_kwin():
    assert kwin.KWinCursor.name == "KWin"


def test_script_path_is_private_and_deterministic(tmp_path):
    from cleverswitch.edgeswitch.linux.kwin import script_path

    path = script_path({"XDG_RUNTIME_DIR": str(tmp_path)})
    assert path == str(tmp_path / "cleverswitch" / "kwin-edge.js")
    write_script(path)
    assert (os.stat(path).st_mode & 0o777) == 0o600
    assert (os.stat(os.path.dirname(path)).st_mode & 0o777) == 0o700
    assert write_script(path) == path


def test_script_path_falls_back_to_the_temp_dir_without_a_runtime_dir(monkeypatch):
    import tempfile

    from cleverswitch.edgeswitch.linux.kwin import script_path

    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    assert script_path({}) == os.path.join(tempfile.gettempdir(), "cleverswitch", "kwin-edge.js")
