#!/bin/bash
set -euo pipefail

APP_NAME="cleverswitch"
PLIST_LABEL="com.user.$APP_NAME"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"

# ── Helpers ──────────────────────────────────────────────────────────

info()  { printf "\033[1;34m==> %s\033[0m\n" "$*"; }
ok()    { printf "\033[1;32m==> %s\033[0m\n" "$*"; }
warn()  { printf "\033[1;33m==> %s\033[0m\n" "$*"; }

# ── Step 1: Stop and remove launch agent ─────────────────────────────

if [ -f "$PLIST_PATH" ]; then
    info "Stopping and removing launch agent..."
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    rm -f "$PLIST_PATH"
    ok "Launch agent removed."
else
    info "No launch agent found — skipping."
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

# ── Done ─────────────────────────────────────────────────────────────

echo ""
ok "Uninstall complete!"
