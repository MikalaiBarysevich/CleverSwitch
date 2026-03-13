"""HID++ 1.0 and 2.0 protocol implementation.

Protocol references:
  - Solaar: lib/logitech_receiver/base.py
  - docs/hidpp-protocol.md
"""

from __future__ import annotations

import logging
import struct
from time import time

from ..errors import TransportError
from .constants import (
    CHANGE_HOST_FN_SET,
    FEATURE_ROOT,
    MAP_FLAG_DIVERTED,
    MSG_DJ_LEN,
    MSG_LONG_LEN,
    MSG_SHORT_LEN,
    REPORT_DJ,
    REPORT_LONG,
    REPORT_SHORT,
    SW_ID,
)
from .transport import HIDTransport

log = logging.getLogger(__name__)

# Expected message lengths by report ID
_MSG_LENGTHS = {
    REPORT_SHORT: MSG_SHORT_LEN,
    REPORT_LONG: MSG_LONG_LEN,
    REPORT_DJ: MSG_DJ_LEN,
}


# ── Internal helpers ──────────────────────────────────────────────────────────


def _pack_params(params: tuple) -> bytes:
    if not params:
        return b""
    parts = []
    for p in params:
        if isinstance(p, int):
            parts.append(struct.pack("B", p))
        else:
            parts.append(bytes(p))
    return b"".join(parts)


def _build_msg(devnumber: int, request_id: int, params: bytes) -> bytes:
    """Assemble a complete HID++ long message (report 0x11, 20 bytes).

    Always uses long format — HID++ 2.0 responses are always long, and on
    Windows each report type is a separate HID collection. Sending long
    ensures request and response use the same collection handle.
    """
    data = struct.pack("!H", request_id) + params
    return struct.pack("!BB18s", REPORT_LONG, devnumber, data)


def _is_relevant(raw: bytes) -> bool:
    """Return True if raw bytes look like a well-formed HID++ or DJ message."""
    return bool(raw) and len(raw) >= 3 and raw[0] in _MSG_LENGTHS and len(raw) == _MSG_LENGTHS[raw[0]]


# ── Request / reply ───────────────────────────────────────────────────────────


def request(
    transport: HIDTransport,
    devnumber: int,
    request_id: int,
    *params,
    timeout: int = 500,
) -> bytes | None:
    """Send a HID++ request and return the reply payload.

    Returns the bytes *after* the two-byte (sub_id, address) prefix — i.e.
    the actual data starting at byte 4 of the raw message.
    Returns None on timeout, error, or no reply expected.

    Protocol notes:
    - SW_ID is OR'd into the low nibble of request_id so we can tell our
      replies apart from notifications (which have sw_id == 0).
    """
    request_id = (request_id & 0xFFF0) | SW_ID

    params_bytes = _pack_params(params)
    request_data = struct.pack("!H", request_id) + params_bytes
    msg = _build_msg(devnumber, request_id, params_bytes)

    if log.isEnabledFor(logging.DEBUG):
        log.debug("-> dev=0x%02X [%s]", devnumber, msg.hex())

    try:
        transport.write(msg)
    except Exception as e:
        raise TransportError(f"write failed: {e}") from e

    deadline = time() + timeout / 1000
    while time() < deadline:
        try:
            raw = transport.read(timeout)
        except Exception as e:
            raise TransportError(f"read failed: {e}") from e

        if not raw or not _is_relevant(raw):
            continue

        if log.isEnabledFor(logging.DEBUG):
            log.debug("<- dev=0x%02X [%s]", raw[1], raw.hex())

        rdev = raw[1]
        rdata = raw[2:]  # starts at sub_id byte

        # Accept reply from this device (Bluetooth may XOR devnumber with 0xFF)
        if rdev != devnumber and rdev != (devnumber ^ 0xFF):
            continue

        # HID++ 1.0 error: sub_id=0x8F, next 2 bytes mirror our request
        if raw[0] == REPORT_SHORT and rdata[0:1] == b"\x8f" and rdata[1:3] == request_data[:2]:
            log.debug("HID++ 1.0 error 0x%02X for request 0x%04X", rdata[3], request_id)
            return None

        # HID++ 2.0 error: sub_id=0xFF, next 2 bytes mirror our request
        if rdata[0:1] == b"\xff" and rdata[1:3] == request_data[:2]:
            log.warning("HID++ 2.0 error 0x%02X for request 0x%04X", rdata[3], request_id)
            return None

        # Successful reply: first 2 bytes of payload match our request_id
        if rdata[:2] == request_data[:2]:
            return rdata[2:]

    log.debug("Timeout (%.1fs) on request 0x%04X from device 0x%02X", timeout, request_id, devnumber)
    return None


def request_write_only(
    transport: HIDTransport,
    devnumber: int,
    request_id: int,
    *params,
) -> None:
    request_id = (request_id & 0xFFF0) | SW_ID

    params_bytes = _pack_params(params)
    msg = _build_msg(devnumber, request_id, params_bytes)

    if log.isEnabledFor(logging.DEBUG):
        log.debug("-> dev=0x%02X [%s]", devnumber, msg.hex())

    try:
        transport.write(msg)
    except Exception as e:
        raise TransportError(f"write failed: {e}") from e


# ── HID++ 2.0 feature operations ─────────────────────────────────────────────


def resolve_feature_index(
    transport: HIDTransport,
    devnumber: int,
    feature_code: int,
) -> int | None:
    """Look up the feature table index for *feature_code* on the given device.

    Sends a ROOT (0x0000) GetFeature request.
    Returns the feature index (1-255), or None if not supported.
    """
    # ROOT feature is at index 0; GetFeature is function 0x00
    request_id = (FEATURE_ROOT << 8) | 0x00
    reply = request(
        transport,
        devnumber,
        request_id,
        feature_code >> 8,
        feature_code & 0xFF,
        0x00,
        timeout=500,
    )
    if reply and reply[0] != 0x00:
        return reply[0]
    return None


def get_device_name(
    transport: HIDTransport,
    devnumber: int,
    feat_idx: int,
) -> str | None:
    """Call x0005 getDeviceNameCount [fn 0] then getDeviceName [fn 1] to read the full name.

    Always uses long messages, so each chunk returns up to 16 characters.
    Returns the marketing name (e.g. 'MX Keys'), or None on failure.
    """
    # fn [0]: getDeviceNameCount — returns total name length (no terminating zero)
    reply = request(transport, devnumber, (feat_idx << 8) | 0x00, timeout=500)
    if not reply:
        return None
    name_len = reply[0]
    if name_len == 0:
        return None

    # fn [1]: getDeviceName(charIndex) — returns chunk starting at charIndex
    chars: list[int] = []
    while len(chars) < name_len:
        reply = request(transport, devnumber, (feat_idx << 8) | 0x10, len(chars), timeout=500)
        if not reply:
            break
        remaining = name_len - len(chars)
        chunk = reply[:remaining]
        if not chunk:
            break
        chars.extend(chunk)

    return bytes(chars).decode("utf-8", errors="replace") if chars else None


def get_device_type(
    transport: HIDTransport,
    devnumber: int,
    feat_idx: int,
) -> int | None:
    """Call x0005 getDeviceType() [function 2] and return the deviceType byte.

    Per x0005 spec: function [2] uses request_id = (feat_idx << 8) | 0x20.
    Returns the deviceType integer (0=Keyboard, 3=Mouse, 4=Trackpad, 5=Trackball),
    or None on failure.
    """
    request_id = (feat_idx << 8) | 0x20  # function [2]
    reply = request(transport, devnumber, request_id, timeout=500)
    if reply:
        return reply[0]
    return None


def send_change_host(
    transport: HIDTransport,
    devnumber: int,
    feature_idx: int,
    target_host: int,
) -> None:
    """Switch *devnumber* to *target_host* (0-based). Fire-and-forget — no reply expected."""
    request_id = (feature_idx << 8) | (CHANGE_HOST_FN_SET & 0xF0) | SW_ID
    params = struct.pack("B", target_host)
    msg = _build_msg(devnumber, request_id, params)
    if log.isEnabledFor(logging.DEBUG):
        log.debug("send_change_host -> dev=0x%02X host=%d [%s]", devnumber, target_host, msg.hex())
    try:
        transport.write(msg)
    except Exception as e:
        raise TransportError(f"send_change_host write failed: {e}") from e


def set_cid_divert(
    transport: HIDTransport,
    devnumber: int,
    feat_idx: int,
    cid: int,
    diverted: bool,
) -> None:
    """Set or clear the temporary DIVERTED flag for *cid* via setCidReporting (fn 0x30).

    Uses only MAP_FLAG_DIVERTED (not PERSISTENTLY_DIVERTED) — some devices
    (e.g. MX Keys S) reject requests that include unsupported flags.

    Payload layout: CID (2 bytes BE) + bfield (1 byte) + remap (2 bytes BE, always 0).
    """
    bfield = MAP_FLAG_DIVERTED << 1  # valid/mask bit — always set
    if diverted:
        bfield |= MAP_FLAG_DIVERTED  # action bit — only when diverting
    params = struct.pack("!HBH", cid, bfield, 0)
    request_write_only(transport, devnumber, (feat_idx << 8) | 0x30, params)
