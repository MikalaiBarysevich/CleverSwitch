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

from ..errors.errors import TransportError
from .constants import (
    HIDPP_USAGE_PAGES,
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
    ("bus_type", ctypes.c_int),
]

# ── hidapi function signatures ────────────────────────────────────────────────

_lib.hid_enumerate.restype = ctypes.POINTER(_DeviceInfo)
_lib.hid_enumerate.argtypes = [ctypes.c_ushort, ctypes.c_ushort]

_lib.hid_free_enumeration.restype = None
_lib.hid_free_enumeration.argtypes = [ctypes.POINTER(_DeviceInfo)]

_lib.hid_open_path.restype = ctypes.c_void_p
_lib.hid_open_path.argtypes = [ctypes.c_char_p]

_lib.hid_open.restype = ctypes.c_void_p
_lib.hid_open.argtypes = [ctypes.c_ushort, ctypes.c_ushort, ctypes.c_wchar_p]

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

# hid_send_output_report — hidapi >= 0.15, uses HidD_SetOutputReport (control pipe).
# More reliable for Bluetooth on Windows (GATT Write With Response vs Write Without Response).
_hid_send_output_report = getattr(_lib, "hid_send_output_report", None)
if _hid_send_output_report is not None:
    _hid_send_output_report.restype = ctypes.c_int
    _hid_send_output_report.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_ubyte),
        ctypes.c_size_t,
    ]
    log.debug("hidapi: hid_send_output_report available (>= 0.15)")


def _hid_err(dev: int | None = None) -> str:
    msg = _lib.hid_error(dev)
    return msg if msg else "unknown hidapi error"


# ── Platform helpers ──────────────────────────────────────────────────────────

_IS_LINUX = _SYSTEM == "Linux"
_IS_WINDOWS = _SYSTEM == "Windows"


def _is_hidpp_interface(info: dict) -> bool:
    """True if this enumeration entry is the HID++ interface."""
    return info["usage_page"] in HIDPP_USAGE_PAGES


def enumerate_hid_devices(
    vendor_id: int = LOGITECH_VENDOR_ID, product_id: int = 0, verbose_extra: bool = False
) -> dict[int, list[HidDeviceInfo]]:
    """Call hid_enumerate and return HID++ capable devices (receivers + BT), freeing the linked list."""
    head = _lib.hid_enumerate(vendor_id, product_id)
    result: dict[int, list[HidDeviceInfo]] = {}
    seen_paths: set[bytes] = set()
    node = head
    while node:
        hid_device_content = node.contents
        node = hid_device_content.next
        pid = hid_device_content.product_id
        bus_type = hid_device_content.bus_type
        path = hid_device_content.path

        if hid_device_content.usage_page not in HIDPP_USAGE_PAGES:
            continue

        # in linux all connected receiver devices are opened as separate hid device.
        # We want to skip them to make the rest
        # code multiplatform
        if (
            _IS_LINUX
            and bus_type == 0x01
            and hid_device_content.serial_number is not None
            and len(hid_device_content.serial_number) > 0
        ):
            continue

        if path in seen_paths:
            continue
        seen_paths.add(path)

        hid_device_info = HidDeviceInfo(
            hid_device_content.path,
            hid_device_content.vendor_id,
            hid_device_content.product_id,
            hid_device_content.usage_page,
            hid_device_content.usage,
            "receiver" if bus_type == 0x01 else "bluetooth",
        )

        pid_collections = result.get(pid, list[HidDeviceInfo]())
        pid_collections.append(hid_device_info)
        result[pid] = pid_collections

    _lib.hid_free_enumeration(head)
    _log(f"All suitable hid devices={result}", verbose_extra)
    return dict(result)


def _log(msg: str, verbose_extra: bool = False) -> None:
    if verbose_extra:
        log.debug(msg)


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

    def __init__(self, kind: str, path: bytes) -> None:
        self._kind = kind
        self._path = path
        self._dev = None
        self.try_open()
        log.debug("Opened %s path=%s", kind, path)

    # ── sync I/O (used by discovery / protocol layer) ─────────────────────────

    def try_open(self) -> None:
        self._dev: int | None = _lib.hid_open_path(self._path)
        if not self._dev:
            raise OSError(_hid_err())

    def try_reopen(self) -> None:
        self.close()
        self.try_open()

    def read(self, timeout: int = -1) -> bytes | None:
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

    def write_output_report(self, msg: bytes) -> None:
        """Write via HidD_SetOutputReport (control pipe).

        Uses GATT Write With Response on BT — more reliable than WriteFile
        (GATT Write Without Response). Falls back to hid_write if hidapi < 0.15.
        """
        if _hid_send_output_report is None:
            self.write(msg)
            return
        buf = (ctypes.c_ubyte * len(msg))(*msg)
        n = _hid_send_output_report(self._dev, buf, len(msg))
        if n < 0:
            raise TransportError(f"hid_send_output_report failed: {_hid_err(self._dev)}")

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def close(self) -> None:
        if self._dev is not None:
            _lib.hid_close(self._dev)
            self._dev = None

    def __repr__(self) -> str:
        return f"HIDTransport(kind={self.kind!r}, pid=0x{self.pid:04X})"
