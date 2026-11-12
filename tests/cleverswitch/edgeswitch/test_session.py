import pytest

from cleverswitch.edgeswitch.session import LinuxSession, detect_linux_session


def _no_sockets(_pattern):
    return []


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"WAYLAND_DISPLAY": "wayland-1", "DISPLAY": ":1"}, LinuxSession.WAYLAND),
        ({"XDG_SESSION_TYPE": "Wayland", "DISPLAY": ":0"}, LinuxSession.WAYLAND),
        ({"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"}, LinuxSession.X11),
        ({"DISPLAY": ":0"}, LinuxSession.X11),
        ({}, LinuxSession.UNKNOWN),
        ({"XDG_RUNTIME_DIR": "/run/user/1000"}, LinuxSession.UNKNOWN),
    ],
)
def test_detects_session_from_environment(env, expected):
    assert detect_linux_session(env, _no_sockets) == expected


def test_wayland_socket_in_runtime_dir_means_wayland():
    seen = []

    def find(pattern):
        seen.append(pattern)
        return ["/run/user/1000/wayland-0"]

    assert detect_linux_session({"XDG_RUNTIME_DIR": "/run/user/1000"}, find) == LinuxSession.WAYLAND
    assert seen == ["/run/user/1000/wayland-*"]
