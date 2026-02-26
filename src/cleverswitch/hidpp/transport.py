"""Low-level HID device access.

This is the only module that imports the `hid` library.
All other modules go through HIDTransport.
"""

from __future__ import annotations

import logging
import platform

import hid

from .constants import (
    ALL_RECEIVER_PIDS,
    BOLT_PID,
    BT_PRODUCT_IDS,
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
        self._dev = hid.Device(pid = pid, path = path)
        log.debug("Opened %s transport pid=0x%04X path=%s", kind, pid, path)

    def read(self, timeout_ms: int = 1000) -> bytes | None:
        """Read one HID packet. Returns None on timeout."""
        data = self._dev.read(MAX_READ_SIZE, timeout_ms)

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
    found = []
    for pid in ALL_RECEIVER_PIDS:
        kind = "bolt" if pid == BOLT_PID else "unifying"
        for info in hid.enumerate(LOGITECH_VENDOR_ID, pid):
            print(f"Checking: Interface {info.get('interface_number')}, Usage Page: {info.get('usage_page')}")
            if not _is_hidpp_interface(info):
                continue
            path = info["path"]
            try:
                t = HIDTransport(path, kind, pid)
                found.append(t)
                log.info("Found %s receiver pid=0x%04X path=%s", kind, pid, path)
            except OSError as e:
                log.warning("Cannot open %s receiver at %s: %s", kind, path, e)
    return found


def find_bluetooth_transports() -> list[tuple[HIDTransport, int]]:
    """Return (transport, btid) for every known Logitech BT device found."""
    found = []
    for btid in BT_PRODUCT_IDS:
        for info in hid.enumerate(LOGITECH_VENDOR_ID, btid):
            path = info["path"]
            try:
                t = HIDTransport(path, "bluetooth", btid)
                found.append((t, btid))
                log.info("Found Bluetooth device btid=0x%04X path=%s", btid, path)
            except OSError as e:
                log.warning("Cannot open BT device 0x%04X at %s: %s", btid, path, e)
    return found
