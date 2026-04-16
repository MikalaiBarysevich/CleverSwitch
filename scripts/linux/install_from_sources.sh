#!/bin/bash
set -euo pipefail

APP_NAME="cleverswitch"
UDEV_RULE="42-cleverswitch.rules"

# ── Helpers ──────────────────────────────────────────────────────────

info()  { printf "\033[1;34m==> %s\033[0m\n" "$*"; }
ok()    { printf "\033[1;32m==> %s\033[0m\n" "$*"; }
warn()  { printf "\033[1;33m==> %s\033[0m\n" "$*"; }
error() { printf "\033[1;31m==> %s\033[0m\n" "$*"; exit 1; }

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

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# ── Step 1: Python ───────────────────────────────────────────────────

if command -v python3 &>/dev/null; then
    PYTHON="$(command -v python3)"
    ok "Python found: $PYTHON ($($PYTHON --version))"
else
    error "Python 3 is not installed. Install it with your package manager (e.g. sudo apt install python3 python3-pip)."
fi

# ── Step 2: CleverSwitch ─────────────────────────────────────────────

info "Installing CleverSwitch..."
"$PYTHON" -m pip install "$PROJECT_DIR"

BINARY_PATH="$(command -v "$APP_NAME" 2>/dev/null || true)"
[ -n "$BINARY_PATH" ] && [ -x "$BINARY_PATH" ] || error "CleverSwitch binary not found after install. You may need to add ~/.local/bin to your PATH."

ok "CleverSwitch installed at: $BINARY_PATH"

# ── Step 3: udev rules ──────────────────────────────────────────────

RULES_SRC="$PROJECT_DIR/rules.d/$UDEV_RULE"
RULES_DST="/etc/udev/rules.d/$UDEV_RULE"

if [ -f "$RULES_DST" ]; then
    ok "udev rules already installed."
else
    info "udev rules are required for non-root HID access."
    if [ ! -f "$RULES_SRC" ]; then
        error "udev rules file not found at $RULES_SRC"
    fi
    if ask_yes_no "Install udev rules? (requires sudo)"; then
        sudo cp "$RULES_SRC" "$RULES_DST"
        sudo udevadm control --reload-rules
        sudo udevadm trigger
        ok "udev rules installed. Unplug and replug your receiver."
    else
        warn "Skipped. CleverSwitch will need root privileges without udev rules."
    fi
fi

# ── Step 4: Autostart (optional) ─────────────────────────────────────

if ask_yes_no "Start CleverSwitch automatically on login?"; then
    AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
    DESKTOP_FILE="$AUTOSTART_DIR/$APP_NAME.desktop"

    mkdir -p "$AUTOSTART_DIR"

    cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=CleverSwitch
Exec=$BINARY_PATH
Hidden=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
Comment=Synchronize Logitech Easy-Switch host switching
EOF

    ok "Autostart entry created at $DESKTOP_FILE"
else
    info "Skipped. You can run CleverSwitch manually with: cleverswitch"
fi

# ── Done ─────────────────────────────────────────────────────────────

echo ""
ok "Setup complete!"
