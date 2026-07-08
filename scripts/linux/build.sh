#!/bin/bash
set -euo pipefail

# Build the CleverSwitch Linux release archive: a PyInstaller onefile binary
# packed with the docs, config example, install scripts, and udev rules.
# Output: dist/cleverswitch_linux.tar.gz

APP_NAME="cleverswitch"
ARCHIVE="cleverswitch_linux"

# ── Helpers ──────────────────────────────────────────────────────────

info()  { printf "\033[1;34m==> %s\033[0m\n" "$*"; }
ok()    { printf "\033[1;32m==> %s\033[0m\n" "$*"; }
warn()  { printf "\033[1;33m==> %s\033[0m\n" "$*"; }
error() { printf "\033[1;31m==> %s\033[0m\n" "$*"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT_DIR"

# ── Step 1: Runtime dependencies ─────────────────────────────────────
# PyInstaller only bundles what is importable at build time — it does NOT
# read pyproject.toml. A missing runtime dep is silently dropped (build-log
# warning only) and the binary then crashes at launch with ModuleNotFoundError.
# This is exactly how the broken v1.2.5 release shipped.

info "Installing runtime dependencies..."
pip install .
pip install pyinstaller

info "Sanity-checking imports..."
python -c "import yaml; print('pyyaml ok')" || error "pyyaml not importable — aborting before a broken build."

# ── Step 2: PyInstaller ──────────────────────────────────────────────
# libhidapi is a system library on Linux; no bundling needed.
# --hidden-import yaml is a safety net against a missed auto-detect.

info "Building binary with PyInstaller..."
pyinstaller --onefile --name "$APP_NAME" --paths src --hidden-import yaml \
    src/cleverswitch/__main__.py

# ── Step 3: Smoke-test ───────────────────────────────────────────────
# Catch a dropped dependency here instead of on a user's machine.

info "Smoke-testing the binary..."
"dist/$APP_NAME" --version || error "Binary failed to start — a build dependency was likely dropped (see step 1)."

# ── Step 4: Assemble archive ─────────────────────────────────────────
# .tar.gz preserves the executable bit; zip does not reliably.

info "Assembling $ARCHIVE.tar.gz..."
stage="dist/$ARCHIVE"
rm -rf "$stage"
mkdir -p "$stage"
cp "dist/$APP_NAME" README.md LICENSE.txt docs/Installation.md config.example.yaml "$stage/"
cp scripts/linux/install.sh scripts/linux/uninstall.sh "$stage/"
cp rules.d/42-cleverswitch.rules "$stage/"
tar -czf "dist/$ARCHIVE.tar.gz" -C dist "$ARCHIVE"
rm -rf "$stage"

# ── Done ─────────────────────────────────────────────────────────────

ok "Release archive ready: dist/$ARCHIVE.tar.gz"
