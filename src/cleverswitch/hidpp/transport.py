"""Low-level HID device access.

This is the only module that imports the `hid` library.
All other modules go through HIDTransport.
"""

from __future__ import annotations

import ctypes.util
import logging
import platform

import hid

# On macOS, hidapi ≥ 0.12.0 added hid_darwin_set_open_exclusive(int).
# Calling it with 0 switches from kIOHIDOptionsTypeSeizeDevice to
# kIOHIDOptionsTypeNone, allowing coexistence with Logi Options+.
# Must be called before any hid.Device() / hid.open() call.
#
# ctypes.util.find_library("hidapi") returns None on Apple Silicon because
# /opt/homebrew/lib is not in the standard search path, so we try known
# Homebrew paths explicitly.
if platform.system() == "Darwin":
    _hidapi_candidates = [
        ctypes.util.find_library("hidapi"),  # works on Intel / if DYLD_LIBRARY_PATH set
        "/opt/homebrew/lib/libhidapi.dylib",  # Apple Silicon Homebrew
        "/usr/local/lib/libhidapi.dylib",  # Intel Homebrew
        "libhidapi.dylib",  # already loaded in process (last resort)
    ]
    _log = logging.getLogger(__name__)
    for _candidate in _hidapi_candidates:
        if not _candidate:
            continue
        try:
            _hidapi = ctypes.CDLL(_candidate)
        except OSError:
            continue
        _set_excl = getattr(_hidapi, "hid_darwin_set_open_exclusive", None)
        if _set_excl is None:
            _log.warning(
                "macOS: hidapi at %s lacks hid_darwin_set_open_exclusive (hidapi < 0.12.0) — run 'brew upgrade hidapi'",
                _candidate,
            )
            break
        _set_excl.argtypes = [ctypes.c_int]
        _set_excl.restype = None
        _set_excl(0)
        _log.debug(
            "macOS: hid_darwin_set_open_exclusive(0) via %s — non-exclusive HID access enabled",
            _candidate,
        )
        break
    else:
        _log.warning("macOS: hidapi not found — run 'brew install hidapi'")

from .constants import (
    ALL_RECEIVER_PIDS,
    BOLT_PID,
    HID_INTERFACE,
    HIDPP_USAGE_PAGE,
    LOGITECH_VENDOR_ID,
    MAX_READ_SIZE,
)

log = logging.getLogger(__name__)

_IS_LINUX = platform.system() == "Linux"


def _is_hidpp_interface(info: dict) -> bool:
    """Return True if this HID enumeration entry is the HID++ interface."""
    if _IS_LINUX:
        # Linux reliably reports interface_number
        return info.get("interface_number") == HID_INTERFACE
    else:
        # Windows / macOS: interface_number is -1; filter by usage_page
        return info.get("usage_page") == HIDPP_USAGE_PAGE


class HIDTransport:
    """Wraps a single open HID device (receiver or Bluetooth device)."""

    def __init__(self, path: bytes, kind: str, pid: int):
        """
        :param path: HID device path as returned by hid.enumerate()
        :param kind: "bolt" | "unifying" | "bluetooth"
        :param pid: USB / BT product ID
        """
        self.path = path
        self.kind = kind
        self.pid = pid
        self._dev = hid.Device(pid=pid, path=path)
        log.debug("Opened %s transport pid=0x%04X path=%s", kind, pid, path)

    def read(self) -> bytes | None:
        """Read one HID packet. Returns None on timeout."""
        data = self._dev.read(MAX_READ_SIZE)

        return bytes(data) if data else None

    def write(self, msg: bytes) -> None:
        """Write one HID packet. msg must start with the report ID."""
        self._dev.write(bytes(msg))

    def close(self) -> None:
        try:
            self._dev.close()
        except Exception:
            pass

    def __repr__(self) -> str:
        return f"HIDTransport(kind={self.kind!r}, pid=0x{self.pid:04X})"


def find_receiver_transports() -> list[HIDTransport]:
    """Return an open HIDTransport for every Bolt/Unifying receiver found."""
    found = {}
    for pid in ALL_RECEIVER_PIDS:
        kind = "bolt" if pid == BOLT_PID else "unifying"
        for info in hid.enumerate(LOGITECH_VENDOR_ID, pid):
            log.debug(f"Checking: Interface {info.get('interface_number')}, Usage Page: {info.get('usage_page')}")
            if not _is_hidpp_interface(info):
                continue
            path = info["path"]
            if path in found:
                continue
            try:
                t = HIDTransport(path, kind, pid)
                found[path] = t
                log.info("Found %s receiver pid=0x%04X path=%s", kind, pid, path)
            except OSError as e:
                log.warning("Cannot open %s receiver at %s: %s", kind, path, e)
    return list(found.values())


def find_bluetooth_transports() -> list[tuple[HIDTransport, int]]:
    """Return (transport, pid) for every non-receiver Logitech HID++ device found.

    Enumerates all Logitech USB/BT products, filters by HID++ usage page (0xFF00)
    to identify direct-connect (Bluetooth / USB direct) HID++ devices, and skips
    known receiver PIDs.
    """
    found = []
    receiver_pids = set(ALL_RECEIVER_PIDS)
    seen_paths: set[bytes] = set()
    for info in hid.enumerate(LOGITECH_VENDOR_ID, 0):  # 0 = all product IDs
        pid = info["product_id"]
        if pid in receiver_pids:
            continue
        if info.get("usage_page") != HIDPP_USAGE_PAGE:
            continue
        path = info["path"]
        if path in seen_paths:
            continue
        seen_paths.add(path)
        try:
            t = HIDTransport(path, "bluetooth", pid)
            found.append((t, pid))
            log.info("Found direct device pid=0x%04X path=%s", pid, path)
        except OSError as e:
            log.warning("Cannot open device 0x%04X at %s: %s", pid, path, e)
    return found
