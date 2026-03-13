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

# ── Step 1: Remove autostart entry ───────────────────────────────────

DESKTOP_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/$APP_NAME.desktop"

if [ -f "$DESKTOP_FILE" ]; then
    info "Removing autostart entry..."
    rm -f "$DESKTOP_FILE"
    ok "Autostart entry removed."
else
    info "No autostart entry found — skipping."
fi

# ── Step 2: Uninstall CleverSwitch ───────────────────────────────────

if pip3 show "$APP_NAME" &>/dev/null; then
    info "Uninstalling CleverSwitch..."
    pip3 uninstall -y "$APP_NAME"
    ok "CleverSwitch uninstalled."
else
    info "CleverSwitch is not installed — skipping."
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
