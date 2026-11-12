from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping

from ...errors.errors import EdgeSwitchError
from ..edge_detector import EdgeDetector
from ..edge_sink import EdgeSink
from ..loop_backend import InputLoop, LoopFactory
from .edge_bus import Bus, EdgeBus, has_owner
from .gnome_shell import SHELL, STATE_CHANGED_MATCH, GnomeShellLoop, decode_state, probe_extension
from .hyprland_locator import HyprlandLocator
from .kwin import KWIN, KWinCursor
from .libinput import Libinput
from .libinput_loop import SEAT, BindingFactory, LibinputLoop
from .xcb import Xcb
from .xinput_loop import XInputLoop

log = logging.getLogger(__name__)

LocatorFactory = Callable[[], HyprlandLocator | None]
BusFactory = Callable[[], Bus]
DISPLAY_HINT = "; on X11 run 'systemctl --user import-environment DISPLAY XAUTHORITY', then restart CleverSwitch"


# libinput only sees the seat it is assigned; a session on another seat would track no keys at all.
def seat_name(env: Mapping[str, str]) -> str:
    return env.get("XDG_SEAT") or SEAT


# DISPLAY is set under Wayland too, for XWayland; only a session without Wayland markers can be X11.
def is_x11_env(env: Mapping[str, str]) -> bool:
    return bool(env.get("DISPLAY")) and not env.get("WAYLAND_DISPLAY") and env.get("XDG_SESSION_TYPE") != "wayland"


def unavailable_message(env: Mapping[str, str]) -> str:
    session = env.get("XDG_SESSION_TYPE", "unknown")
    desktop = env.get("XDG_CURRENT_DESKTOP", "unknown")
    message = (
        "it needs X11, Hyprland, KDE Plasma 6 or GNOME; this desktop does not share the cursor position "
        f"(XDG_SESSION_TYPE={session}, XDG_CURRENT_DESKTOP={desktop})"
    )
    if session != "wayland" and not env.get("DISPLAY") and not env.get("WAYLAND_DISPLAY"):
        message += DISPLAY_HINT
    return message


def _looks_like_hyprland(env: Mapping[str, str]) -> bool:
    return bool(env.get("HYPRLAND_INSTANCE_SIGNATURE")) or "hyprland" in env.get("XDG_CURRENT_DESKTOP", "").lower()


# Two cases: Hyprland is running but its socket did not answer, or no socket was found at all (usually a
# systemd unit without XDG_RUNTIME_DIR, or a stale HYPRLAND_INSTANCE_SIGNATURE).
def hyprland_socket_message(socket_found: bool) -> str:
    if socket_found:
        return (
            "Hyprland did not answer on its IPC socket; edge switch needs Hyprland's own session, and the "
            "socket may be stale after a restart (it retries when a device connects)"
        )
    return (
        "Hyprland is the session but no IPC socket was found; edge switch needs $XDG_RUNTIME_DIR (or "
        "HYPRLAND_INSTANCE_SIGNATURE) in CleverSwitch's environment. Under systemd, run "
        "'systemctl --user import-environment XDG_RUNTIME_DIR HYPRLAND_INSTANCE_SIGNATURE', then restart "
        "CleverSwitch"
    )


# Runs on the backend thread at every start attempt, so a desktop that appears later is found on a revive.
# X11 goes first, so a stale Hyprland socket left in the runtime dir cannot take over a real X session.
def linux_loop_factory(
    detector_factory: Callable[[], EdgeDetector],
    env: Mapping[str, str] = os.environ,
    xcb_factory: Callable[[], Xcb] = Xcb,
    binding_factory: BindingFactory = Libinput,
    locator_factory: LocatorFactory = HyprlandLocator.detect,
    bus_factory: BusFactory | None = None,
) -> LoopFactory:
    if bus_factory is None:
        bus_factory = _session_bus_factory(env)

    def build(publish, stopping) -> InputLoop:
        sink = EdgeSink(detector_factory(), publish, stopping)
        if is_x11_env(env) and (xcb := _connect_x11(xcb_factory)) is not None:
            try:
                return XInputLoop(xcb, sink)
            except BaseException:
                xcb.close()
                raise
        locator = locator_factory()
        if locator is not None and locator.probe():
            return LibinputLoop(binding_factory, sink, locator, seat=seat_name(env))
        if (loop := _from_session_bus(bus_factory, sink, binding_factory, env)) is not None:
            return loop
        if _looks_like_hyprland(env):
            # A Hyprland session without a usable socket is a fixable setup problem, not an unsupported desktop.
            raise EdgeSwitchError(hyprland_socket_message(locator is not None))
        raise EdgeSwitchError(unavailable_message(env))

    return build


def _connect_x11(xcb_factory: Callable[[], Xcb]) -> Xcb | None:
    try:
        xcb = xcb_factory()
    except OSError as e:
        log.debug(f"Edge switch cannot use X11: {e}")
        return None
    if xcb.is_xwayland():
        log.debug("Edge switch skips XWayland")
        xcb.close()
        return None
    return xcb


# KDE and GNOME are found on the bus rather than from XDG_CURRENT_DESKTOP, which systemd units often lack.
def _from_session_bus(
    bus_factory: BusFactory, sink: EdgeSink, binding_factory: BindingFactory, env: Mapping[str, str]
) -> InputLoop | None:
    try:
        bus = bus_factory()
    except (OSError, ImportError) as e:
        log.debug(f"Edge switch cannot reach the session bus: {e}")
        return None
    try:
        if has_owner(bus, KWIN):
            # A step that fails closes what it was given; closing the bus twice is harmless.
            return LibinputLoop(binding_factory, sink, KWinCursor(EdgeBus(bus, KWIN)), seat=seat_name(env))
        if has_owner(bus, SHELL):
            if (problem := probe_extension(bus)) is not None:
                raise EdgeSwitchError(problem)
            return GnomeShellLoop(EdgeBus(bus, SHELL, decode_state, (STATE_CHANGED_MATCH,)), sink)
    except BaseException:
        bus.close()
        raise
    bus.close()
    return None


def _session_bus_factory(env: Mapping[str, str]) -> BusFactory:
    def open_bus() -> Bus:
        from .session_bus import SessionBus  # jeepney is only needed here

        return SessionBus(env)

    return open_bus
