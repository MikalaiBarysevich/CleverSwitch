import json
import pathlib
import threading
from unittest.mock import MagicMock

import pytest

from cleverswitch.edgeswitch.geometry import EDGE_TOLERANCE_PX
from cleverswitch.edgeswitch.linux.edge_bus import BUS_NAME, INTERFACE, OBJECT_PATH, EdgeBus
from cleverswitch.edgeswitch.linux.gnome_shell import (
    EXTENSION_UUID,
    EXTENSIONS_INTERFACE,
    README_HINT,
    SHELL,
    STATE_CHANGED_MATCH,
    GnomeShellLoop,
    decode_state,
    probe_extension,
)
from cleverswitch.model.config.edge import Edge
from cleverswitch.model.config.modifier import Modifier

from .fake_bus import PEER_OWNER, FakeBus, call, signal

EXTENSION_DIR = pathlib.Path(__file__).parents[4] / "gnome-extension" / EXTENSION_UUID
CTRL, SHIFT, ALT, MOD4, BUTTON1, SUPER = 1 << 2, 1 << 0, 1 << 3, 1 << 6, 1 << 8, 1 << 26


@pytest.mark.parametrize(
    ("mask", "expected"),
    [
        (0, (Modifier.NONE, False)),
        (CTRL, (Modifier.CTRL, False)),
        (CTRL | SHIFT | ALT, (Modifier.CTRL | Modifier.SHIFT | Modifier.ALT, False)),
        (MOD4, (Modifier.META, False)),
        (SUPER, (Modifier.META, False)),
        (CTRL | BUTTON1, (Modifier.CTRL, True)),
        (1 << 1, (Modifier.NONE, False)),  # caps lock is not a modifier here
    ],
)
def test_decode_state(mask, expected):
    assert decode_state(mask) == expected


@pytest.mark.parametrize("mask", [True, 1.0, "4"])
def test_decode_state_rejects_non_integers(mask):
    with pytest.raises(ValueError):
        decode_state(mask)


def _shell_bus(enabled=True, info=None):
    return FakeBus(
        owners={SHELL: PEER_OWNER},
        results={
            (SHELL, "Get"): (("b", enabled),),
            (SHELL, "GetExtensionInfo"): ({} if info is None else info,),
        },
    )


@pytest.mark.parametrize(
    ("enabled", "info", "expected"),
    [
        (True, {"state": ("d", 1.0)}, None),
        (False, {"state": ("d", 1.0)}, "user extensions turned off"),
        (True, {}, "is not installed"),
        (True, {"state": ("d", 2.0)}, f"gnome-extensions enable {EXTENSION_UUID}"),
        (True, {"state": ("d", 3.0)}, "failed to load"),
        (True, {"state": ("d", 4.0)}, "does not support this GNOME version"),
        (True, {"state": ("d", 6.0)}, "is not active (state 6)"),
        (True, {"state": ("s", "x")}, "is not installed"),
    ],
)
def test_probe_extension(enabled, info, expected):
    problem = probe_extension(_shell_bus(enabled, info))
    if expected is None:
        assert problem is None
    else:
        assert expected in problem
        assert problem.endswith(README_HINT)


def _loop(stopping=lambda: False):
    bus = _shell_bus()
    edge_bus = EdgeBus(bus, SHELL, decode_state, (STATE_CHANGED_MATCH,))
    sink = MagicMock()
    return GnomeShellLoop(edge_bus, sink), bus, sink


def test_extension_state_is_watched_before_the_name_is_taken():
    _, bus, _ = _loop()
    members = [c[3] for c in bus.calls]
    # Both watches, then the peer, then our name: a subscription added after the owner lookup could miss a
    # restart that happens in between, and RequestName is what the extension reacts to.
    assert members == ["AddMatch", "AddMatch", "GetNameOwner", "RequestName"]
    assert bus.calls[1][4] == (STATE_CHANGED_MATCH,)


def test_state_then_edges_reach_the_sink_and_interrupt_ends_run():
    loop, bus, sink = _loop()
    sink.on_edges.side_effect = lambda _edges: threading.Thread(target=loop.interrupt).start()
    bus.push(call("State", CTRL), call("Edges", 1))
    loop.run()
    sink.on_state.assert_called_once_with(Modifier.CTRL, False)
    sink.on_edges.assert_called_once_with(frozenset({Edge.LEFT}))


def test_interrupt_before_run_returns_after_one_drain():
    loop, bus, sink = _loop()
    loop.interrupt()
    loop.run()


def _state_changed(uuid, state):
    return signal(
        "ExtensionStateChanged", uuid, {"state": ("d", state)}, sender=PEER_OWNER, interface=EXTENSIONS_INTERFACE
    )


def test_extension_turned_off_ends_run():
    loop, bus, _ = _loop()
    bus.push(_state_changed(EXTENSION_UUID, 2.0))
    with pytest.raises(OSError, match="turned off"):
        loop.run()


def test_other_extensions_and_signals_are_ignored():
    loop, bus, sink = _loop()
    sink.on_edges.side_effect = lambda _edges: threading.Thread(target=loop.interrupt).start()
    bus.push(
        _state_changed("other@example.com", 2.0),
        _state_changed(EXTENSION_UUID, 1.0),
        signal("Something", sender=PEER_OWNER, interface="other"),
        call("Edges", 0),
    )
    loop.run()


def test_close_closes_the_bus_and_the_pipe():
    loop, bus, _ = _loop()
    loop.close()
    assert bus.closed
    assert loop._wake_r is None


def test_failed_pipe_closes_the_bus(monkeypatch):
    import os

    bus = _shell_bus()
    edge_bus = EdgeBus(bus, SHELL, decode_state)

    def no_pipe():
        raise OSError("too many files")

    monkeypatch.setattr(os, "pipe", no_pipe)
    with pytest.raises(OSError):
        GnomeShellLoop(edge_bus, MagicMock())
    assert bus.closed


def test_extension_matches_the_python_side():
    metadata = json.loads((EXTENSION_DIR / "metadata.json").read_text())
    assert metadata["uuid"] == EXTENSION_UUID
    assert all(int(v) >= 45 for v in metadata["shell-version"])
    script = (EXTENSION_DIR / "extension.js").read_text()
    for constant in (BUS_NAME, OBJECT_PATH, INTERFACE):
        assert f"'{constant}'" in script
    assert f"TOLERANCE = {EDGE_TOLERANCE_PX:g};" in script
