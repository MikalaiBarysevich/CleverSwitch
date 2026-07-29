#!/bin/bash
set -euo pipefail

# Install and start CleverSwitch as a systemd *user* service.
# A user service (not system) is required so the daemon runs inside the seated
# graphical session that owns the udev `uaccess` ACL granting non-root HID access.

APP_NAME="cleverswitch"
UNIT_NAME="$APP_NAME.service"
INSTALL_PATH="$HOME/.local/bin/$APP_NAME"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_DST="$UNIT_DIR/$UNIT_NAME"

# ── Helpers ──────────────────────────────────────────────────────────

info()  { printf "\033[1;34m==> %s\033[0m\n" "$*"; }
ok()    { printf "\033[1;32m==> %s\033[0m\n" "$*"; }
warn()  { printf "\033[1;33m==> %s\033[0m\n" "$*"; }
error() { printf "\033[1;31m==> %s\033[0m\n" "$*"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
UNIT_SRC="$SCRIPT_DIR/$UNIT_NAME"

[ -f "$UNIT_SRC" ] || error "Unit file not found at $UNIT_SRC."
command -v systemctl >/dev/null 2>&1 || error "systemctl not found — this system does not use systemd."
systemctl --user show-environment >/dev/null 2>&1 || error "No systemd user session available. Log in to a graphical session and try again."

# ── Resolve the binary ───────────────────────────────────────────────
# Prefer the canonical install location so the unit survives PATH changes and
# stale binaries elsewhere on PATH; fall back to `which` for manual/pip installs.

if [ -x "$INSTALL_PATH" ]; then
    BINARY_PATH="$INSTALL_PATH"
else
    BINARY_PATH="$(command -v "$APP_NAME" 2>/dev/null || true)"
fi

[ -n "$BINARY_PATH" ] || error "$APP_NAME not found at $INSTALL_PATH or on your PATH. Install it first."

info "Found $APP_NAME at: $BINARY_PATH"

# ── Migrate away from the old XDG autostart entry ────────────────────
# Earlier versions launched CleverSwitch via ~/.config/autostart/*.desktop.
# Leaving it in place would start a second instance alongside the service.

OLD_DESKTOP="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/$APP_NAME.desktop"
if [ -f "$OLD_DESKTOP" ]; then
    rm -f "$OLD_DESKTOP"
    info "Removed old autostart entry at $OLD_DESKTOP (superseded by the systemd service)."
fi

if [ -f "/etc/systemd/user/$UNIT_NAME" ]; then
    warn "A system-wide unit exists at /etc/systemd/user/$UNIT_NAME."
    warn "The per-user unit installed below takes precedence; remove the old one with:"
    warn "  sudo rm /etc/systemd/user/$UNIT_NAME"
fi

# ── Install the unit ─────────────────────────────────────────────────
# Copy the template, then pin ExecStart to the resolved absolute path.

info "Installing user service to $UNIT_DST..."
mkdir -p "$UNIT_DIR"
sed "s|^ExecStart=.*|ExecStart=$BINARY_PATH|" "$UNIT_SRC" > "$UNIT_DST"

systemctl --user daemon-reload
systemctl --user enable "$UNIT_NAME"
systemctl --user restart "$UNIT_NAME"

ok "$APP_NAME service enabled and started."
info "Status:  systemctl --user status $UNIT_NAME"
info "Logs:    journalctl --user -u $UNIT_NAME -f"
warn "The service runs inside your graphical session — it starts at login, not"
warn "at boot before login (which is what the udev HID access rule requires)."
