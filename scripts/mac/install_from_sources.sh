#!/bin/bash
set -euo pipefail

APP_NAME="cleverswitch"

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

# ── Step 1: Homebrew ─────────────────────────────────────────────────

if command -v brew &>/dev/null; then
    ok "Homebrew is already installed."
else
    info "Homebrew not found. Installing..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

    # Add brew to PATH for the rest of this script (Apple Silicon vs Intel)
    if [ -f /opt/homebrew/bin/brew ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [ -f /usr/local/bin/brew ]; then
        eval "$(/usr/local/bin/brew shellenv)"
    fi

    command -v brew &>/dev/null || error "Homebrew installation failed."
    ok "Homebrew installed."
fi

# ── Step 2: Python ───────────────────────────────────────────────────

if brew list python &>/dev/null; then
    ok "Python is already installed via Homebrew."
else
    info "Installing Python via Homebrew..."
    brew install python
    ok "Python installed."
fi

PYTHON="$(brew --prefix python)/libexec/bin/python"
if [ ! -x "$PYTHON" ]; then
    PYTHON="$(brew --prefix)/bin/python3"
fi
[ -x "$PYTHON" ] || error "Could not find Homebrew Python."
info "Using Python: $PYTHON ($($PYTHON --version))"

# ── Step 3: pipx ─────────────────────────────────────────────────────
# pipx, not pip: Homebrew Python is externally managed, so PEP 668 rejects
# `pip install` outside a venv. Homebrew's pipx is a standalone binary that
# `$PYTHON -m pipx` cannot import, so always drive the executable on PATH.

if command -v pipx &>/dev/null; then
    ok "pipx is already installed."
else
    info "Installing pipx via Homebrew..."
    brew install pipx
    command -v pipx &>/dev/null || error "pipx installation failed."
    ok "pipx installed."
fi

# pipx links entry points into ~/.local/bin, which is not on the default macOS
# PATH. `ensurepath` fixes future shells; export it for the checks below.
pipx ensurepath >/dev/null 2>&1 || true
export PATH="$HOME/.local/bin:$PATH"

# ── Step 4: CleverSwitch ─────────────────────────────────────────────

info "Installing CleverSwitch..."
pipx install --force --python "$PYTHON" "$PROJECT_DIR"

BINARY_PATH="$(command -v "$APP_NAME" 2>/dev/null || true)"
[ -n "$BINARY_PATH" ] && [ -x "$BINARY_PATH" ] || error "CleverSwitch binary not found after install. You may need to add ~/.local/bin to your PATH."

ok "CleverSwitch installed at: $BINARY_PATH"

# ── Step 5: Launch at startup (optional) ─────────────────────────────

if ask_yes_no "Start CleverSwitch automatically on login?"; then
    bash "$SCRIPT_DIR/setup_startup.command"
else
    info "Skipped. You can run CleverSwitch manually with: cleverswitch"
fi

# ── Done ─────────────────────────────────────────────────────────────

echo ""
ok "Setup complete!"
