from unittest.mock import MagicMock

import pytest

from cleverswitch.edgeswitch.edge_detector import EdgeDetector
from cleverswitch.edgeswitch.linux.desktop import DISPLAY_HINT, is_x11_env, linux_loop_factory
from cleverswitch.errors.errors import EdgeSwitchError
from cleverswitch.model.config.edge import Edge
from cleverswitch.model.config.modifier import Modifier

from .fake_bus import PEER_OWNER, FakeBus

X11 = {"DISPLAY": ":0", "XDG_SESSION_TYPE": "x11", "XDG_CURRENT_DESKTOP": "XFCE"}
HYPRLAND = {"DISPLAY": ":1", "WAYLAND_DISPLAY": "wayland-1", "XDG_SESSION_TYPE": "wayland"}
KDE = {"DISPLAY": ":1", "WAYLAND_DISPLAY": "wayland-0", "XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "KDE"}


@pytest.fixture
def loops(mocker):
    xinput = mocker.patch("cleverswitch.edgeswitch.linux.desktop.XInputLoop", autospec=True)
    libinput = mocker.patch("cleverswitch.edgeswitch.linux.desktop.LibinputLoop", autospec=True)
    return xinput, libinput


def _xcb(xwayland=False):
    xcb = MagicMock()
    xcb.is_xwayland.return_value = xwayland
    return xcb


def _locator(probe_ok=True):
    locator = MagicMock()
    locator.probe.return_value = probe_ok
    return locator


def _build(env, xcb_factory=None, locator=None, bus=None):
    detector = EdgeDetector(frozenset({Edge.LEFT}), Modifier.CTRL, 0)
    binding = MagicMock()
    bus = bus or FakeBus()
    factory = linux_loop_factory(
        lambda: detector, env, xcb_factory or (lambda: _xcb()), binding, lambda: locator, lambda: bus
    )
    return factory(MagicMock(), lambda: False)


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        (X11, True),
        ({"DISPLAY": ":0"}, True),
        (HYPRLAND, False),
        ({"DISPLAY": ":1", "XDG_SESSION_TYPE": "wayland"}, False),
        ({"XDG_SESSION_TYPE": "x11"}, False),
        ({}, False),
    ],
)
def test_is_x11_env(env, expected):
    assert is_x11_env(env) is expected


def test_x11_gets_the_xinput_loop(loops):
    xinput, libinput = loops
    xcb = _xcb()
    assert _build(X11, lambda: xcb, _locator()) is xinput.return_value
    assert xinput.call_args.args[0] is xcb
    libinput.assert_not_called()


def test_hyprland_gets_the_libinput_loop_without_touching_x11(loops):
    xinput, libinput = loops
    xcb_factory = MagicMock()
    locator = _locator()
    assert _build(HYPRLAND, xcb_factory, locator) is libinput.return_value
    assert libinput.call_args.args[2] is locator
    xcb_factory.assert_not_called()


def test_libinput_is_given_the_session_seat(loops):
    _, libinput = loops
    _build({**HYPRLAND, "XDG_SEAT": "seat1"}, locator=_locator())
    assert libinput.call_args.kwargs["seat"] == "seat1"

    _build(HYPRLAND, locator=_locator())
    assert libinput.call_args.kwargs["seat"] == "seat0"


def test_xwayland_is_skipped_and_closed(loops):
    xinput, libinput = loops
    xcb = _xcb(xwayland=True)
    env = {"DISPLAY": ":1"}  # a systemd unit that only imported DISPLAY into a Hyprland session
    assert _build(env, lambda: xcb, _locator()) is libinput.return_value
    xcb.close.assert_called_once()
    xinput.assert_not_called()


def test_unreachable_x_server_falls_through_to_hyprland(loops):
    _, libinput = loops

    def refuse():
        raise OSError("cannot connect to the X server")

    assert _build(X11, refuse, _locator()) is libinput.return_value


def test_failed_x11_setup_closes_the_connection(loops):
    xinput, _ = loops
    xinput.side_effect = OSError("no XInput")
    xcb = _xcb()
    with pytest.raises(OSError, match="no XInput"):
        _build(X11, lambda: xcb, _locator())
    xcb.close.assert_called_once()


@pytest.mark.parametrize("locator", [None, _locator(probe_ok=False)])
def test_other_desktops_are_unavailable(loops, locator):
    with pytest.raises(EdgeSwitchError, match="XDG_SESSION_TYPE=wayland, XDG_CURRENT_DESKTOP=KDE") as error:
        _build(KDE, locator=locator)
    assert DISPLAY_HINT not in str(error.value)


def test_missing_display_gets_the_import_hint(loops):
    with pytest.raises(EdgeSwitchError, match="XDG_SESSION_TYPE=unknown") as error:
        _build({})
    assert str(error.value).endswith(DISPLAY_HINT)


def test_every_attempt_detects_again(loops):
    _, libinput = loops
    locators = [None, _locator()]
    detector = EdgeDetector(frozenset({Edge.LEFT}), Modifier.CTRL, 0)
    build = linux_loop_factory(lambda: detector, KDE, MagicMock(), MagicMock(), lambda: locators.pop(0), FakeBus)
    with pytest.raises(EdgeSwitchError):
        build(MagicMock(), lambda: False)
    assert build(MagicMock(), lambda: False) is libinput.return_value


def test_kde_gets_the_libinput_loop_with_kwin(loops, mocker):
    _, libinput = loops
    kwin_cursor = mocker.patch("cleverswitch.edgeswitch.linux.desktop.KWinCursor", autospec=True)
    bus = FakeBus(owners={"org.kde.KWin": PEER_OWNER})
    assert _build(KDE, bus=bus) is libinput.return_value
    assert libinput.call_args.args[2] is kwin_cursor.return_value
    edge_bus = kwin_cursor.call_args.args[0]
    assert edge_bus.bus is bus
    assert not bus.closed


def test_a_failed_kde_start_closes_the_bus(loops, mocker):
    mocker.patch("cleverswitch.edgeswitch.linux.desktop.KWinCursor", side_effect=OSError("no script"))
    bus = FakeBus(owners={"org.kde.KWin": PEER_OWNER})
    with pytest.raises(OSError, match="no script"):
        _build(KDE, bus=bus)
    assert bus.closed


def test_a_bus_without_a_known_compositor_is_closed(loops):
    bus = FakeBus()
    with pytest.raises(EdgeSwitchError):
        _build(KDE, bus=bus)
    assert bus.closed


@pytest.mark.parametrize("error", [OSError("no bus"), ImportError("no jeepney")])
def test_no_session_bus_is_unavailable(loops, error):
    def broken():
        raise error

    detector = EdgeDetector(frozenset({Edge.LEFT}), Modifier.CTRL, 0)
    build = linux_loop_factory(lambda: detector, KDE, MagicMock(), MagicMock(), lambda: None, broken)
    with pytest.raises(EdgeSwitchError, match="KDE Plasma 6"):
        build(MagicMock(), lambda: False)


def test_default_bus_factory_opens_the_session_bus(mocker):
    session_bus = mocker.patch("cleverswitch.edgeswitch.linux.session_bus.SessionBus")
    from cleverswitch.edgeswitch.linux.desktop import _session_bus_factory

    assert _session_bus_factory(KDE)() is session_bus.return_value
    session_bus.assert_called_once_with(KDE)


def _gnome_bus(state=1.0):
    return FakeBus(
        owners={"org.gnome.Shell": PEER_OWNER},
        results={
            ("org.gnome.Shell", "Get"): (("b", True),),
            ("org.gnome.Shell", "GetExtensionInfo"): ({"state": ("d", state)},),
        },
    )


GNOME = {"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "GNOME", "WAYLAND_DISPLAY": "wayland-0"}


def test_gnome_gets_the_gnome_shell_loop(loops, mocker):
    gnome_loop = mocker.patch("cleverswitch.edgeswitch.linux.desktop.GnomeShellLoop", autospec=True)
    bus = _gnome_bus()
    assert _build(GNOME, bus=bus) is gnome_loop.return_value
    assert gnome_loop.call_args.args[0].bus is bus
    assert not bus.closed


def test_gnome_without_the_extension_says_how_to_enable_it(loops):
    bus = _gnome_bus(state=2.0)
    with pytest.raises(EdgeSwitchError, match="gnome-extensions enable"):
        _build(GNOME, bus=bus)
    assert bus.closed


HYPR_ENV = {"XDG_SESSION_TYPE": "wayland", "WAYLAND_DISPLAY": "wayland-1", "HYPRLAND_INSTANCE_SIGNATURE": "abc"}


def test_hyprland_without_a_socket_says_what_is_missing(loops):
    with pytest.raises(EdgeSwitchError, match="no IPC socket was found") as error:
        _build(HYPR_ENV, locator=None)
    assert "import-environment" in str(error.value)


def test_hyprland_whose_socket_does_not_answer_is_not_called_unsupported(loops):
    with pytest.raises(EdgeSwitchError, match="did not answer") as error:
        _build(HYPR_ENV, locator=_locator(probe_ok=False), bus=FakeBus())
    assert "does not share the cursor position" not in str(error.value)
