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
# libhidapi is loaded at runtime via ctypes.CDLL, which PyInstaller cannot
# detect — it must be bundled explicitly or the binary only works on distros
# that already have libhidapi-hidraw installed. transport.py looks for it in _MEIPASS.
# Its only deps are libudev and libc; build on the oldest distro you support.
# --hidden-import yaml is a safety net against a missed auto-detect.

HIDAPI_SO="$(ldconfig -p | awk '/libhidapi-hidraw\.so\.0 / && !found {print $NF; found = 1}')"
if [ -z "$HIDAPI_SO" ] || [ ! -f "$HIDAPI_SO" ]; then
    info "libhidapi-hidraw.so.0 not found on this system — building it from source."
    "$ROOT_DIR/scripts/build_hidapi.sh"
    HIDAPI_SO="$ROOT_DIR/build/hidapi/install/lib/libhidapi-hidraw.so.0"
    [ -f "$HIDAPI_SO" ] || error "hidapi source build did not produce $HIDAPI_SO."
fi
info "Bundling $HIDAPI_SO"

info "Building binary with PyInstaller..."
pyinstaller --onefile --name "$APP_NAME" --paths src --hidden-import yaml --copy-metadata cleverswitch \
    --add-binary "$HIDAPI_SO:." \
    src/cleverswitch/__main__.py

# ── Step 3: Smoke-test ───────────────────────────────────────────────
# Catch a dropped dependency here instead of on a user's machine.

info "Smoke-testing the binary..."
"dist/$APP_NAME" --version || error "Binary failed to start — a build dependency was likely dropped (see step 1)."
# --version succeeds here even without the bundle (system hidapi is on this machine), so check the archive.
pyi-archive_viewer --list "dist/$APP_NAME" | grep -q "libhidapi-hidraw.so.0" \
    || error "libhidapi-hidraw.so.0 is missing from the binary — it would fail on distros without it."

# ── Step 4: Assemble archive ─────────────────────────────────────────
# .tar.gz preserves the executable bit; zip does not reliably.

info "Assembling $ARCHIVE.tar.gz..."
stage="dist/$ARCHIVE"
rm -rf "$stage"
mkdir -p "$stage"
cp "dist/$APP_NAME" README.md LICENSE.txt docs/Installation.md config.example.yaml "$stage/"
cp scripts/linux/install.sh scripts/linux/uninstall.sh scripts/linux/setup_startup.sh "$stage/"
cp scripts/linux/cleverswitch.service "$stage/"
cp rules.d/42-cleverswitch.rules "$stage/"
tar -czf "dist/$ARCHIVE.tar.gz" -C dist "$ARCHIVE"
rm -rf "$stage"

# ── Done ─────────────────────────────────────────────────────────────

ok "Release archive ready: dist/$ARCHIVE.tar.gz"
