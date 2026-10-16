#!/bin/bash
set -euo pipefail

# Download, verify, and build hidapi from source for the macOS/Linux release
# binaries, used by scripts/{mac,linux}/build.sh when no system hidapi is found.
# Installs into build/hidapi/install; the library lands in build/hidapi/install/lib.
# Requires curl, cmake, and a C compiler (plus libudev-dev on Linux).

HIDAPI_VERSION="0.15.0"
HIDAPI_SHA256="5d84dec684c27b97b921d2f3b73218cb773cf4ea915caee317ac8fc73cef8136"
HIDAPI_URL="https://github.com/libusb/hidapi/archive/refs/tags/hidapi-$HIDAPI_VERSION.tar.gz"

info()  { printf "\033[1;34m==> %s\033[0m\n" "$*"; }
error() { printf "\033[1;31m==> %s\033[0m\n" "$*"; exit 1; }

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORK_DIR="$ROOT_DIR/build/hidapi"
TARBALL="$WORK_DIR/hidapi-$HIDAPI_VERSION.tar.gz"
SRC_DIR="$WORK_DIR/hidapi-hidapi-$HIDAPI_VERSION"

command -v cmake >/dev/null || error "cmake is required to build hidapi from source."

mkdir -p "$WORK_DIR"
info "Downloading hidapi $HIDAPI_VERSION..."
curl -fsSL -o "$TARBALL" "$HIDAPI_URL" || error "Download failed: $HIDAPI_URL"

if command -v sha256sum >/dev/null; then
    actual="$(sha256sum "$TARBALL" | awk '{print $1}')"
else
    actual="$(shasum -a 256 "$TARBALL" | awk '{print $1}')"
fi
[ "$actual" = "$HIDAPI_SHA256" ] || error "hidapi checksum mismatch: expected $HIDAPI_SHA256, got $actual"

rm -rf "$SRC_DIR" "$WORK_DIR/build" "$WORK_DIR/install"
tar -xzf "$TARBALL" -C "$WORK_DIR"

info "Building hidapi $HIDAPI_VERSION..."
cmake -S "$SRC_DIR" -B "$WORK_DIR/build" -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_LIBDIR=lib \
    -DHIDAPI_WITH_LIBUSB=OFF -DHIDAPI_BUILD_HIDTEST=OFF >/dev/null
cmake --build "$WORK_DIR/build" --config Release >/dev/null
cmake --install "$WORK_DIR/build" --prefix "$WORK_DIR/install" >/dev/null
