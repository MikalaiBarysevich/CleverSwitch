import json
import logging
import os
import socket
import threading

import pytest

from cleverswitch.edgeswitch.geometry import Rect
from cleverswitch.edgeswitch.linux import hyprland_locator
from cleverswitch.edgeswitch.linux.hyprland_locator import (
    HyprlandLocator,
    parse_bounds,
    parse_cursor,
    request,
    socket_candidates,
)

ONE_MONITOR = [{"x": 0, "y": 0, "width": 1920, "height": 1080, "scale": 1.0, "transform": 0}]


def _monitor(x=0, y=0, width=1920, height=1080, scale=1.0, transform=0, **extra):
    return {"x": x, "y": y, "width": width, "height": height, "scale": scale, "transform": transform, **extra}


class FakeHyprland:
    """Answers j/cursorpos and j/monitors per socket path; a path in `dead` raises like a refused connect."""

    def __init__(self, cursor=(100, 200), monitors=ONE_MONITOR, dead=()):
        self.cursor = cursor
        self.monitors = monitors
        self.dead = set(dead)
        self.calls = []

    def __call__(self, path, command):
        self.calls.append((path, command))
        if path in self.dead:
            raise ConnectionRefusedError("no socket")
        if command == b"j/cursorpos":
            return json.dumps({"x": self.cursor[0], "y": self.cursor[1]}).encode()
        if command == b"j/monitors":
            return json.dumps(self.monitors).encode()
        raise AssertionError(command)


def _locator(fake, paths=("/run/hypr/a/.socket.sock",)):
    return HyprlandLocator(lambda: list(paths), request=fake)


def test_parse_cursor():
    assert parse_cursor(b'\n{\n    "x": 1091,\n    "y": 727\n}\n') == (1091.0, 727.0)


@pytest.mark.parametrize("reply", [b"not json", b'{"x": 1}', b"[]"])
def test_parse_cursor_rejects_a_bad_reply(reply):
    with pytest.raises((ValueError, KeyError, TypeError)):
        parse_cursor(reply)


def test_bounds_of_one_monitor():
    assert parse_bounds(json.dumps(ONE_MONITOR).encode()) == Rect(0, 0, 1920, 1080)


def test_bounds_are_the_union_of_monitors():
    monitors = [_monitor(x=-1920, y=0), _monitor(x=0, y=-200, width=2560, height=1440)]
    assert parse_bounds(json.dumps(monitors).encode()) == Rect(-1920, -200, 2560, 1240)


def test_bounds_use_logical_size_and_rotation():
    monitors = [_monitor(width=2560, height=1440, scale=1.5), _monitor(x=1706, width=1920, height=1080, transform=1)]
    bounds = parse_bounds(json.dumps(monitors).encode())
    assert bounds == Rect(0, 0, 1706 + 1080, 1920)


def test_disabled_and_mirrored_monitors_are_skipped():
    monitors = [
        _monitor(),
        _monitor(x=1920, disabled=True),
        _monitor(x=3840, mirrorOf="DP-3"),
        _monitor(mirrorOf="none"),
    ]
    assert parse_bounds(json.dumps(monitors).encode()) == Rect(0, 0, 1920, 1080)


def test_no_usable_monitor_gives_no_bounds():
    assert parse_bounds(json.dumps([_monitor(disabled=True)]).encode()) is None


def test_candidates_put_the_environment_first_then_newest():
    env = {"XDG_RUNTIME_DIR": "/run/user/1000", "HYPRLAND_INSTANCE_SIGNATURE": "b"}
    times = {"/run/user/1000/hypr/a/.socket.sock": 1.0, "/run/user/1000/hypr/c/.socket.sock": 3.0}
    candidates = socket_candidates(env, lambda _base: ["a", "b", "c"], lambda path: times.get(path, 2.0))
    assert candidates == [
        "/run/user/1000/hypr/b/.socket.sock",
        "/run/user/1000/hypr/c/.socket.sock",
        "/run/user/1000/hypr/a/.socket.sock",
    ]


def test_candidates_without_the_environment_scan_the_runtime_dir():
    env = {"XDG_RUNTIME_DIR": "/run/user/1000"}
    assert socket_candidates(env, lambda _base: ["a"], lambda _p: 0.0) == ["/run/user/1000/hypr/a/.socket.sock"]


def test_candidates_survive_unreadable_dirs_and_times():
    def listdir(_base):
        raise FileNotFoundError

    def mtime(_path):
        raise FileNotFoundError

    env = {"XDG_RUNTIME_DIR": "/run/user/1000"}
    assert socket_candidates(env, listdir) == []
    assert socket_candidates(env, lambda _b: ["a"], mtime) == ["/run/user/1000/hypr/a/.socket.sock"]


def test_no_runtime_dir_means_no_candidates():
    assert socket_candidates({}, lambda _b: ["a"]) == []


def test_detect_returns_none_off_hyprland():
    def listdir(_base):
        raise FileNotFoundError

    assert HyprlandLocator.detect({"XDG_RUNTIME_DIR": "/run/user/1000"}, listdir) is None


def test_detect_on_hyprland():
    env = {"XDG_RUNTIME_DIR": "/run/user/1000", "HYPRLAND_INSTANCE_SIGNATURE": "a"}
    assert isinstance(HyprlandLocator.detect(env, lambda _b: []), HyprlandLocator)


def test_probe_picks_the_first_live_candidate():
    fake = FakeHyprland(dead={"/dead"})
    locator = _locator(fake, paths=("/dead", "/live"))
    assert locator.probe()
    assert locator.locate() == (100.0, 200.0, Rect(0, 0, 1920, 1080))
    assert fake.calls[-1] == ("/live", b"j/cursorpos")


def test_probe_fails_when_nothing_answers():
    locator = _locator(FakeHyprland(dead={"/dead"}), paths=("/dead",))
    assert not locator.probe()
    with pytest.raises(OSError, match="not probed"):
        locator.locate()


def test_bounds_are_read_per_locate():
    fake = FakeHyprland()
    locator = _locator(fake)
    locator.probe()
    locator.locate()
    locator.locate()
    assert [c for _p, c in fake.calls].count(b"j/monitors") == 2


@pytest.mark.parametrize("break_it", ["dead", "garbage"])
def test_failure_raises_and_a_new_probe_recovers(break_it):
    fake = FakeHyprland()
    locator = _locator(fake)
    locator.probe()
    if break_it == "dead":
        fake.dead.add("/run/hypr/a/.socket.sock")
    else:
        fake.cursor = ("x", None)
    with pytest.raises(OSError, match="stopped answering"):
        locator.locate()
    fake.dead.clear()
    fake.cursor = (1, 2)
    assert locator.probe()
    assert locator.locate()[:2] == (1.0, 2.0)


def test_probe_logs_the_socket_once(caplog):
    caplog.set_level(logging.DEBUG)
    locator = _locator(FakeHyprland())
    locator.probe()
    locator.probe()
    assert caplog.text.count("reads the cursor through") == 1


def _serve(path, reply, delay_close=None):
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    server.listen(1)
    received = []

    def handle():
        conn, _ = server.accept()
        received.append(conn.recv(64))
        if delay_close is None:
            conn.sendall(reply)
            conn.close()
        else:
            delay_close.wait(2)
            conn.close()
        server.close()

    thread = threading.Thread(target=handle, daemon=True)
    thread.start()
    return thread, received


def test_request_reads_until_eof(tmp_path):
    path = str(tmp_path / "s")
    thread, received = _serve(path, b'{"x": 1, "y": 2}')
    assert request(path, b"j/cursorpos") == b'{"x": 1, "y": 2}'
    thread.join(2)
    assert received == [b"j/cursorpos"]


def test_request_times_out_on_a_silent_server(tmp_path):
    path = str(tmp_path / "s")
    release = threading.Event()
    _serve(path, b"", delay_close=release)
    with pytest.raises(TimeoutError):
        request(path, b"j/cursorpos", timeout=0.05)
    release.set()


def test_request_caps_the_reply(tmp_path, monkeypatch):
    monkeypatch.setattr(hyprland_locator, "MAX_REPLY", 4)
    path = str(tmp_path / "s")
    _serve(path, b"0123456789")
    with pytest.raises(ValueError, match="over 4 bytes"):
        request(path, b"j/monitors")


def test_request_to_a_missing_socket_raises(tmp_path):
    with pytest.raises(OSError):
        request(os.fspath(tmp_path / "missing"), b"j/cursorpos")


def test_locator_is_a_cursor_feed_asked_per_motion():
    from unittest.mock import MagicMock

    fake = FakeHyprland()
    locator = _locator(fake)
    locator.probe()
    sink = MagicMock()
    assert locator.name == "Hyprland"
    assert locator.fd() is None
    locator.drain(sink)
    locator.on_motion(sink)
    assert sink.on_motion.call_args.args[0]() == (100.0, 200.0, Rect(0, 0, 1920, 1080))
    locator.on_motion(sink)
    sink.on_motion.call_args.args[0]()
    locator.close()


def test_health_check_reprobes_the_socket():
    fake = FakeHyprland()
    new = "/run/hypr/new/.socket.sock"
    paths = ["/run/hypr/old/.socket.sock"]

    def moved(path, command):
        if path != new:
            raise ConnectionRefusedError("old socket gone")
        return fake(path, command)

    locator = HyprlandLocator(lambda: list(paths), moved)
    assert not locator.probe(), "the old socket is refused"
    paths.insert(0, new)
    assert locator.health_check(), "a revive finds the socket Hyprland restarted on"
