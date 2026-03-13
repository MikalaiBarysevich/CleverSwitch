"""Low-level HID device access — direct ctypes binding to libhidapi.

Platform-specific library loading:
  Linux   → libhidapi-hidraw.so.0  (hidraw backend, non-exclusive — no kernel driver detach)
  macOS   → libhidapi.dylib        (IOHIDManager)
  Windows → hidapi.dll             (SetupAPI — located next to the cython-hidapi hid.pyd)

All blocking I/O uses hid_read_timeout so callers control the exact wait time.
HIDTransport.read_async / write_async delegate to asyncio.to_thread so the
asyncio event loop in listeners.py stays unblocked while waiting for HID events.
"""

from __future__ import annotations

import ctypes
import dataclasses
import logging
import os
import platform
import sys

from ..errors import TransportError
from .constants import (
    ALL_RECEIVER_PIDS,
    HIDPP_USAGE_PAGES,
    HIDPP_USAGES_LONG,
    LOGITECH_VENDOR_ID,
    MAX_READ_SIZE,
)

log = logging.getLogger(__name__)

_SYSTEM = platform.system()

# ── Platform-specific library candidates ──────────────────────────────────────

# Platform-agnostic search list — try all known names, first match wins.
# Matches Solaar's approach: no platform branching needed.
_LIB_NAMES: list[str] = [
    "libhidapi-hidraw.so.0",  # Linux preferred: hidraw backend (non-exclusive)
    "libhidapi-hidraw.so",
    "libhidapi-libusb.so",
    "libhidapi-libusb.so.0",
    "libhidapi.so.0",
    "libhidapi.so",
    "/opt/homebrew/lib/libhidapi.dylib",  # macOS Apple Silicon (Homebrew)
    "/usr/local/lib/libhidapi.dylib",  # macOS Intel (Homebrew)
    "libhidapi.dylib",
    "hidapi.dll",  # Windows: standalone install
    "libhidapi-0.dll",  # Windows: bundled with cython-hidapi (pip install hidapi)
]

# ── Load the library ──────────────────────────────────────────────────────────

# Python 3.8+ on Windows no longer searches PATH / CWD for DLLs by default.
# Add the Scripts directory (where cleverswitch.exe lives) to the DLL search path.
if _SYSTEM == "Windows":
    _scripts_dir = os.path.join(sys.prefix, "Scripts")
    if os.path.isdir(_scripts_dir):
        os.add_dll_directory(_scripts_dir)
    # PyInstaller bundles files into a temp _MEIPASS directory
    _meipass = getattr(sys, "_MEIPASS", None)
    if _meipass and os.path.isdir(_meipass):
        os.add_dll_directory(_meipass)

_lib: ctypes.CDLL | None = None
for _name in _LIB_NAMES:
    try:
        _lib = ctypes.CDLL(_name)
        log.debug("hidapi: loaded %s", _name)
        break
    except OSError:
        continue

if _lib is None:
    _hint = {
        "Linux": "sudo apt install libhidapi-hidraw0",
        "Darwin": "brew install hidapi",
        "Windows": "pip install hidapi",
    }.get(_SYSTEM, "install hidapi for your platform")
    raise ImportError(f"Cannot load hidapi library — {_hint}")

# ── Initialise hidapi ────────────────────────────────────────────────────────
# hid_init() must be called before hid_darwin_set_open_exclusive() because
# hid_init() resets the exclusive flag to 1 for backward compatibility.
# Without this, the first hid_enumerate() triggers hid_init() which overrides
# our non-exclusive setting.

_lib.hid_init.restype = ctypes.c_int
_lib.hid_init.argtypes = []
_lib.hid_init()

# ── macOS: disable exclusive device opening ───────────────────────────────────
# hid_darwin_set_open_exclusive(0) allows coexistence with Logi Options+.
# Must be called AFTER hid_init() and before the first hid_open_path().

if _SYSTEM == "Darwin":
    _set_excl = getattr(_lib, "hid_darwin_set_open_exclusive", None)
    if _set_excl is not None:
        _set_excl.argtypes = [ctypes.c_int]
        _set_excl.restype = None
        _set_excl(0)
        log.debug("macOS: hid_darwin_set_open_exclusive(0) — non-exclusive access enabled")
    else:
        log.warning("macOS: hidapi < 0.12 — run 'brew upgrade hidapi' to allow coexistence with Logi Options+")


# ── struct hid_device_info ────────────────────────────────────────────────────
# Mirrors the layout from hidapi.h up to and including the `next` pointer.
# The `bus_type` field (added in hidapi 0.12) comes after `next`, so omitting
# it here does not affect the offset of any earlier field.


class _DeviceInfo(ctypes.Structure):
    pass  # forward declaration — required for self-referential struct


_DeviceInfo._fields_ = [
    ("path", ctypes.c_char_p),
    ("vendor_id", ctypes.c_ushort),
    ("product_id", ctypes.c_ushort),
    ("serial_number", ctypes.c_wchar_p),
    ("release_number", ctypes.c_ushort),
    ("manufacturer_string", ctypes.c_wchar_p),
    ("product_string", ctypes.c_wchar_p),
    ("usage_page", ctypes.c_ushort),
    ("usage", ctypes.c_ushort),
    ("interface_number", ctypes.c_int),
    ("next", ctypes.POINTER(_DeviceInfo)),
]

# ── hidapi function signatures ────────────────────────────────────────────────

_lib.hid_enumerate.restype = ctypes.POINTER(_DeviceInfo)
_lib.hid_enumerate.argtypes = [ctypes.c_ushort, ctypes.c_ushort]

_lib.hid_free_enumeration.restype = None
_lib.hid_free_enumeration.argtypes = [ctypes.POINTER(_DeviceInfo)]

_lib.hid_open_path.restype = ctypes.c_void_p
_lib.hid_open_path.argtypes = [ctypes.c_char_p]

_lib.hid_close.restype = None
_lib.hid_close.argtypes = [ctypes.c_void_p]

_lib.hid_read_timeout.restype = ctypes.c_int
_lib.hid_read_timeout.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_ubyte),
    ctypes.c_size_t,
    ctypes.c_int,
]

_lib.hid_write.restype = ctypes.c_int
_lib.hid_write.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_ubyte),
    ctypes.c_size_t,
]

_lib.hid_error.restype = ctypes.c_wchar_p
_lib.hid_error.argtypes = [ctypes.c_void_p]


def _hid_err(dev: int | None = None) -> str:
    msg = _lib.hid_error(dev)
    return msg if msg else "unknown hidapi error"


# ── Platform helpers ──────────────────────────────────────────────────────────

_IS_LINUX = _SYSTEM == "Linux"
_IS_WINDOWS = _SYSTEM == "Windows"


def _is_hidpp_interface(info: dict) -> bool:
    """True if this enumeration entry is the HID++ interface."""
    return info["usage_page"] in HIDPP_USAGE_PAGES


def enumerate_hid_devices(vendor_id: int = LOGITECH_VENDOR_ID, product_id: int = 0) -> list[HidDeviceInfo]:
    """Call hid_enumerate and return HID++ capable devices (receivers + BT), freeing the linked list."""
    head = _lib.hid_enumerate(vendor_id, product_id)
    result: dict[bytes, HidDeviceInfo] = {}
    node = head
    while node:
        hid_device_content = node.contents
        node = hid_device_content.next
        path = hid_device_content.path
        usage_page = hid_device_content.usage_page
        pid = hid_device_content.product_id
        log.debug(f"Found hid device with path={path}, pid=0x{pid:04X}, usage_page=0x{usage_page:04X}")

        if path in result:
            log.debug(f"Already processed path={path}, pid=0x{pid:04X}")
            continue

        if usage_page not in HIDPP_USAGE_PAGES:
            log.debug(f"Usage page not supported. Skipping path={path}, pid=0x{pid:04X}, usage_page=0x{usage_page:04X}")
            continue

        usage = hid_device_content.usage
        if usage not in HIDPP_USAGES_LONG:
            log.debug(f"Usage 0x{usage:04X} not supported. Skipping path={path}, pid=0x{pid:04X}")
            continue

        connection_type = "receiver" if pid in ALL_RECEIVER_PIDS else "bluetooth"

        result[path] = HidDeviceInfo(
            path,
            hid_device_content.vendor_id,
            pid,
            usage_page,
            usage,
            connection_type,
        )
    _lib.hid_free_enumeration(head)
    log.debug(f"All suitable hid devices={result}")
    return list(result.values())


@dataclasses.dataclass
class HidDeviceInfo:
    path: bytes
    vid: int
    pid: int
    usage_page: int
    usage: int
    connection_type: str  # "receiver" or "bluetooth"


# ── HIDTransport ──────────────────────────────────────────────────────────────


class HIDTransport:
    """Owns one open hid_device* handle.

    Sync read/write are used by the discovery thread (protocol.py request loop).
    Async read_async/write_async are used by the monitor coroutine so the asyncio
    event loop is never blocked waiting for HID events.
    """

    def __init__(self, path: bytes, kind: str, pid: int) -> None:
        self.path = path
        self.kind = kind
        self.pid = pid
        self._dev: int | None = _lib.hid_open_path(path)
        if not self._dev:
            raise OSError(_hid_err())
        log.debug("Opened %s pid=0x%04X %s", kind, pid, path)

    # ── sync I/O (used by discovery / protocol layer) ─────────────────────────

    def read(self, timeout: int = 500) -> bytes | None:
        """Block for up to *timeout* ms waiting for one HID packet.

        timeout=0  → non-blocking (return None immediately if no data)
        timeout=-1 → block until data arrives
        timeout>0  → wait at most *timeout* ms

        Returns None on timeout. Raises TransportError on device error.
        """
        if self._dev is None:
            log.warning("read on closed transport")
            raise TransportError("read on closed transport")
        buf = (ctypes.c_ubyte * MAX_READ_SIZE)()
        n = _lib.hid_read_timeout(self._dev, buf, MAX_READ_SIZE, timeout)
        if n < 0:
            log.debug(f"hid_read_timeout failed: {_hid_err(self._dev)}")

            raise TransportError(f"hid_read_timeout failed: {_hid_err(self._dev)}")
        return bytes(buf[:n]) if n > 0 else None

    def write(self, msg: bytes) -> None:
        """Write one HID packet (first byte must be the report ID)."""
        buf = (ctypes.c_ubyte * len(msg))(*msg)
        n = _lib.hid_write(self._dev, buf, len(msg))
        if n < 0:
            raise TransportError(f"hid_write failed: {_hid_err(self._dev)}")

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def close(self) -> None:
        if self._dev is not None:
            _lib.hid_close(self._dev)
            self._dev = None

    def __repr__(self) -> str:
        return f"HIDTransport(kind={self.kind!r}, pid=0x{self.pid:04X})"
