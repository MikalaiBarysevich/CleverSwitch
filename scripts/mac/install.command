#!/bin/bash
set -euo pipefail

APP_NAME="cleverswitch"
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
    warn "Add the following line to your ~/.zshrc or ~/.bash_profile, then restart your terminal:"
    warn "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# ── Step 3: Launch at startup (optional) ─────────────────────────────

if ask_yes_no "Start CleverSwitch automatically on login?"; then
    bash "$SCRIPT_DIR/setup_startup.command"
else
    info "Skipped. You can run CleverSwitch manually with: $APP_NAME"
fi

# ── Done ─────────────────────────────────────────────────────────────

echo ""
ok "Installation complete!"
warn "Note: on first run, macOS will prompt for Input Monitoring permission."
warn "If no prompt appears, grant it manually in System Settings > Privacy & Security > Input Monitoring."
