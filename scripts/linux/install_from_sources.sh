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
    error "Python 3 is not installed. Install it with your package manager (e.g. sudo apt install python3 pipx)."
fi

# ── Step 2: CleverSwitch ─────────────────────────────────────────────

# pipx, not pip: PEP 668 rejects `pip install` outside a venv on Arch,
# Debian 12+, Ubuntu 23.04+ and Fedora 38+. pipx often ships as a standalone
# binary that `python3 -m pipx` cannot import, so prefer the one on PATH.

if command -v pipx &>/dev/null; then
    PIPX=(pipx)
elif "$PYTHON" -m pipx --version &>/dev/null; then
    PIPX=("$PYTHON" -m pipx)
else
    error "pipx is not installed. Install it with your package manager (e.g. sudo pacman -S python-pipx, sudo apt install pipx, sudo dnf install pipx)."
fi

info "Installing CleverSwitch..."
"${PIPX[@]}" install --force --python "$PYTHON" "$PROJECT_DIR"

BINARY_PATH="$(command -v "$APP_NAME" 2>/dev/null || true)"
[ -n "$BINARY_PATH" ] && [ -x "$BINARY_PATH" ] || error "CleverSwitch binary not found after install. You may need to add ~/.local/bin to your PATH."

ok "CleverSwitch installed at: $BINARY_PATH"

# ── Step 3: udev rules ──────────────────────────────────────────────

RULES_SRC="$PROJECT_DIR/rules.d/$UDEV_RULE"
RULES_DST="/etc/udev/rules.d/$UDEV_RULE"

if [ ! -f "$RULES_SRC" ]; then
    error "udev rules file not found at $RULES_SRC"
fi

if [ -f "$RULES_DST" ] && cmp -s "$RULES_SRC" "$RULES_DST"; then
    ok "udev rules already installed."
else
    if [ -f "$RULES_DST" ]; then
        info "The installed udev rules differ from this version's (which also let edge switch read Logitech"
        info "keyboards in /dev/input). Replacing them drops any change you made to $RULES_DST."
        prompt="Replace udev rules? (requires sudo)"
    else
        info "udev rules are required for non-root HID access."
        prompt="Install udev rules? (requires sudo)"
    fi
    if ask_yes_no "$prompt"; then
        sudo cp "$RULES_SRC" "$RULES_DST"
        sudo udevadm control --reload-rules
        sudo udevadm trigger
        ok "udev rules installed. Unplug and replug your receiver."
    else
        warn "Skipped. Without current udev rules CleverSwitch may need root, and edge switch on Hyprland/KDE may not see the keyboard."
    fi
fi

# ── Step 4: Autostart (optional) ─────────────────────────────────────

if ask_yes_no "Start CleverSwitch automatically on login?"; then
    bash "$SCRIPT_DIR/setup_startup.sh"
else
    info "Skipped. You can run CleverSwitch manually with: cleverswitch"
fi

# ── Step 5: Edge switch on GNOME (optional) ──────────────────────────

case "$(printf '%s' "${XDG_CURRENT_DESKTOP:-}" | tr '[:upper:]' '[:lower:]')" in
    *gnome*)
        info "GNOME detected. Edge switch on GNOME needs the bundled GNOME Shell extension:"
        info "see 'Enabling edge switch on KDE / GNOME' in README.md for the install steps."
        ;;
esac

# ── Done ─────────────────────────────────────────────────────────────

echo ""
ok "Setup complete!"
