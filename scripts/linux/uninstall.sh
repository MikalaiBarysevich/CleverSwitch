#!/bin/bash
set -euo pipefail

APP_NAME="cleverswitch"
UDEV_RULE="42-cleverswitch.rules"

# ── Helpers ──────────────────────────────────────────────────────────

info()  { printf "\033[1;34m==> %s\033[0m\n" "$*"; }
ok()    { printf "\033[1;32m==> %s\033[0m\n" "$*"; }
warn()  { printf "\033[1;33m==> %s\033[0m\n" "$*"; }

ask_yes_no() {
    local prompt="$1"
    while true; do
        printf "\033[1;34m==> %s [y/n]: \033[0m" "$prompt"
        read -r answer
        case "$answer" in
            [Yy]*) return 0 ;;
            [Nn]*) return 1 ;;
            *) echo "Please answer y or n." ;;
        esac
    done
}

# ── Step 1: Stop and remove the systemd user service ─────────────────

UNIT_NAME="$APP_NAME.service"
UNIT_DST="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/$UNIT_NAME"

if [ -f "$UNIT_DST" ]; then
    info "Stopping and disabling the systemd user service..."
    systemctl --user disable --now "$UNIT_NAME" 2>/dev/null || true
    rm -f "$UNIT_DST"
    systemctl --user daemon-reload 2>/dev/null || true
    ok "Service removed."
else
    info "No systemd user service found — skipping."
fi

# Legacy: remove the old XDG autostart entry from pre-systemd installs.
DESKTOP_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/$APP_NAME.desktop"

if [ -f "$DESKTOP_FILE" ]; then
    info "Removing old autostart entry..."
    rm -f "$DESKTOP_FILE"
    ok "Autostart entry removed."
fi

# ── Step 2: Remove installed binary ──────────────────────────────────

BINARY_PATH="$HOME/.local/bin/$APP_NAME"

if [ -f "$BINARY_PATH" ]; then
    info "Removing $BINARY_PATH..."
    rm -f "$BINARY_PATH"
    ok "Binary removed."
else
    info "No binary found at $BINARY_PATH — skipping."
fi

# ── Step 3: Uninstall pip package (backward compat) ──────────────────

if pip3 show "$APP_NAME" &>/dev/null; then
    info "Uninstalling CleverSwitch pip package..."
    pip3 uninstall -y "$APP_NAME"
    ok "CleverSwitch pip package uninstalled."
else
    info "CleverSwitch pip package is not installed — skipping."
fi

# ── Step 3: Remove udev rules (optional) ─────────────────────────────

RULES_DST="/etc/udev/rules.d/$UDEV_RULE"

if [ -f "$RULES_DST" ]; then
    if ask_yes_no "Remove udev rules? (requires sudo)"; then
        sudo rm -f "$RULES_DST"
        sudo udevadm control --reload-rules
        sudo udevadm trigger
        ok "udev rules removed."
    else
        info "Keeping udev rules."
    fi
else
    info "No udev rules found — skipping."
fi

# ── Done ─────────────────────────────────────────────────────────────

echo ""
ok "Uninstall complete!"
