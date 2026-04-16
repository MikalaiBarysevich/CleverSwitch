#!/bin/bash
set -euo pipefail

APP_NAME="cleverswitch"
UDEV_RULE="42-cleverswitch.rules"
INSTALL_DIR="$HOME/.local/bin"
INSTALL_PATH="$INSTALL_DIR/$APP_NAME"

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
SRC_BINARY="$SCRIPT_DIR/$APP_NAME"

[ -f "$SRC_BINARY" ] || error "Binary not found at $SRC_BINARY. Run this script from the extracted archive folder."

# ── Step 1: Install binary ────────────────────────────────────────────

info "Installing $APP_NAME to $INSTALL_PATH..."
mkdir -p "$INSTALL_DIR"
cp "$SRC_BINARY" "$INSTALL_PATH"
chmod +x "$INSTALL_PATH"
ok "$APP_NAME installed at $INSTALL_PATH"

# ── Step 2: PATH check ────────────────────────────────────────────────

if echo ":${PATH}:" | grep -q ":${INSTALL_DIR}:"; then
    ok "$INSTALL_DIR is on your PATH."
else
    warn "$INSTALL_DIR is not on your PATH."
    warn "Add the following line to your ~/.bashrc or ~/.profile, then restart your terminal:"
    warn "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# ── Step 3: udev rules ───────────────────────────────────────────────

RULES_SRC="$SCRIPT_DIR/$UDEV_RULE"
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
Exec=$INSTALL_PATH
Hidden=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
Comment=Synchronize Logitech Easy-Switch host switching
EOF

    ok "Autostart entry created at $DESKTOP_FILE"
else
    info "Skipped. You can run CleverSwitch manually with: $APP_NAME"
fi

# ── Done ─────────────────────────────────────────────────────────────

echo ""
ok "Installation complete!"
