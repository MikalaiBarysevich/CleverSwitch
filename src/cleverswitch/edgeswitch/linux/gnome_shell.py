from __future__ import annotations

import logging
import os
import select
from typing import Any

from ...model.config.modifier import Modifier
from ..edge_sink import EdgeSink
from .edge_bus import Bus, BusMessage, EdgeBus

log = logging.getLogger(__name__)

SHELL = "org.gnome.Shell"
SHELL_PATH = "/org/gnome/Shell"
EXTENSIONS_INTERFACE = "org.gnome.Shell.Extensions"
PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"
EXTENSION_UUID = "cleverswitch@mikalaibarysevich.github.io"
README_HINT = " (see 'Enabling edge switch on KDE / GNOME' in the README)"

STATE_ACTIVE = 1
STATE_INACTIVE = 2
STATE_ERROR = 3
STATE_OUT_OF_DATE = 4

# Clutter.ModifierType bits the extension sends.
SHIFT_MASK = 1 << 0
CONTROL_MASK = 1 << 2
MOD1_MASK = 1 << 3  # Alt
MOD4_MASK = 1 << 6  # Super, as most keymaps map it
# Clutter BUTTON1..5: left, middle, right and the two side buttons.
BUTTON_MASKS = (1 << 8) | (1 << 9) | (1 << 10) | (1 << 11) | (1 << 12)
SUPER_MASK = 1 << 26
STATE_MASK = SHIFT_MASK | CONTROL_MASK | MOD1_MASK | MOD4_MASK | SUPER_MASK | BUTTON_MASKS

STATE_CHANGED_MATCH = (
    f"type='signal',sender='{SHELL}',interface='{EXTENSIONS_INTERFACE}',"
    f"member='ExtensionStateChanged',arg0='{EXTENSION_UUID}'"
)


def decode_state(mask: Any) -> tuple[Modifier, bool]:
    if isinstance(mask, bool) or not isinstance(mask, int):
        raise ValueError(f"state mask {mask!r}")
    modifiers = Modifier.NONE
    if mask & CONTROL_MASK:
        modifiers |= Modifier.CTRL
    if mask & SHIFT_MASK:
        modifiers |= Modifier.SHIFT
    if mask & MOD1_MASK:
        modifiers |= Modifier.ALT
    if mask & (MOD4_MASK | SUPER_MASK):
        modifiers |= Modifier.META
    return modifiers, bool(mask & BUTTON_MASKS)


def _unwrap(value: Any) -> Any:
    # jeepney hands a D-Bus variant over as (signature, value).
    if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], str):
        return value[1]
    return value


def extension_state(info: dict) -> int | None:
    state = _unwrap(info.get("state"))
    return int(state) if isinstance(state, int | float) else None


# Why edge switch cannot run on this GNOME Shell, or None when the extension is active.
def probe_extension(bus: Bus) -> str | None:
    enabled = bus.call(
        SHELL, SHELL_PATH, PROPERTIES_INTERFACE, "Get", "ss", (EXTENSIONS_INTERFACE, "UserExtensionsEnabled")
    )
    if not _unwrap(enabled[0]):
        return "GNOME has user extensions turned off" + README_HINT
    info = bus.call(SHELL, SHELL_PATH, EXTENSIONS_INTERFACE, "GetExtensionInfo", "s", (EXTENSION_UUID,))[0]
    state = extension_state(info)
    if state == STATE_ACTIVE:
        return None
    if state is None:
        reason = "is not installed, or GNOME has not loaded it yet (log out and back in after copying it)"
    elif state == STATE_INACTIVE:
        reason = f"is disabled: run 'gnome-extensions enable {EXTENSION_UUID}'"
    elif state == STATE_OUT_OF_DATE:
        reason = "does not support this GNOME version"
    elif state == STATE_ERROR:
        reason = "failed to load; see 'journalctl /usr/bin/gnome-shell'"
    else:
        reason = f"is not active (state {state})"
    return f"the CleverSwitch GNOME Shell extension {reason}" + README_HINT


class GnomeShellLoop:
    """GNOME through the CleverSwitch GNOME Shell extension, which reports the held modifiers, buttons and the
    outer edges under the cursor over the session bus, so GNOME needs no /dev/input access. The extension
    being disabled, or GNOME Shell leaving the bus, raises out of run() until the next revive."""

    def __init__(self, edge_bus: EdgeBus, sink: EdgeSink):
        self._edge_bus = edge_bus
        self._sink = sink
        self._interrupted = False
        self._wake_r: int | None = None
        self._wake_w: int | None = None
        try:
            self._wake_r, self._wake_w = os.pipe()
        except BaseException:
            edge_bus.close()
            raise
        log.info("Edge switch reads the keys and the cursor position from GNOME Shell")

    def run(self) -> None:
        poller = select.poll()
        poller.register(self._wake_r, select.POLLIN)
        poller.register(self._edge_bus.fd(), select.POLLIN)
        while not self._interrupted:
            self._edge_bus.drain(self._sink, self._on_signal)
            poller.poll()

    def interrupt(self) -> None:
        self._interrupted = True
        os.write(self._wake_w, b"x")

    def close(self) -> None:
        self._edge_bus.close()
        for fd in (self._wake_r, self._wake_w):
            if fd is not None:
                os.close(fd)
        self._wake_r = self._wake_w = None

    def _on_signal(self, message: BusMessage) -> None:
        if message.member != "ExtensionStateChanged" or message.interface != EXTENSIONS_INTERFACE:
            return
        uuid, info = message.body
        if uuid == EXTENSION_UUID and extension_state(info) != STATE_ACTIVE:
            raise OSError("the CleverSwitch GNOME Shell extension was turned off")
