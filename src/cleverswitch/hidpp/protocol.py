"""HID++ 1.0 and 2.0 protocol implementation.

Protocol references:
  - Solaar: lib/logitech_receiver/base.py
  - docs/hidpp-protocol.md
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from time import time

from .constants import (
    CHANGE_HOST_FN_GET,
    CHANGE_HOST_FN_SET,
    DEVICE_RECEIVER,
    FEATURE_ROOT,
    MAP_FLAG_DIVERTED,
    MSG_DJ_LEN,
    MSG_LONG_LEN,
    MSG_SHORT_LEN,
    REG_PAIRING_INFO_BOLT,
    REG_PAIRING_INFO_UNIFYING,
    REG_RECEIVER_INFO,
    REPORT_DJ,
    REPORT_LONG,
    REPORT_SHORT,
    SW_ID,
    MAP_FLAG_PERSISTENTLY_DIVERTED,
    HOST_SWITCH_CIDS
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


def _build_msg(devnumber: int, request_id: int, params: bytes, long: bool = False) -> bytes:
    """Assemble a complete HID++ message including report ID prefix."""
    data = struct.pack("!H", request_id) + params
    if long or len(data) > MSG_SHORT_LEN - 2:
        return struct.pack("!BB18s", REPORT_LONG, devnumber, data)
    return struct.pack("!BB5s", REPORT_SHORT, devnumber, data)


def _is_relevant(raw: bytes) -> bool:
    """Return True if raw bytes look like a well-formed HID++ or DJ message."""
    return bool(raw) and len(raw) >= 3 and raw[0] in _MSG_LENGTHS and len(raw) == _MSG_LENGTHS[raw[0]]


# ── Request / reply ───────────────────────────────────────────────────────────

def request(
        transport: HIDTransport,
        devnumber: int,
        request_id: int,
        *params,
        long: bool = False,
        timeout: float = 4.0,
) -> bytes | None:
    """Send a HID++ request and return the reply payload.

    Returns the bytes *after* the two-byte (sub_id, address) prefix — i.e.
    the actual data starting at byte 4 of the raw message.
    Returns None on timeout, error, or no reply expected.

    Protocol notes:
    - For HID++ 2.0 device requests (devnumber != 0xFF or request_id < 0x8000):
        SW_ID is OR'd into the low nibble of request_id so we can tell our
        replies apart from notifications (which have sw_id == 0).
    - For HID++ 1.0 register reads to the receiver (devnumber == 0xFF,
        request_id >= 0x8000): SW_ID is NOT added (it would corrupt the register
        number). Register 0x83B5 replies additionally must match the first param.
    """
    # Add SW_ID for device requests and HID++ 2.0 receiver requests
    is_receiver_register = devnumber == DEVICE_RECEIVER and request_id >= 0x8000
    if not is_receiver_register:
        request_id = (request_id & 0xFFF0) | SW_ID

    params_bytes = _pack_params(params)
    request_data = struct.pack("!H", request_id) + params_bytes
    msg = _build_msg(devnumber, request_id, params_bytes, long)

    if log.isEnabledFor(logging.DEBUG):
        log.debug("-> dev=0x%02X [%s]", devnumber, msg.hex())

    try:
        transport.write(msg)
    except Exception as e:
        from ..errors import TransportError
        raise TransportError(f"write failed: {e}") from e

    deadline = time() + timeout
    while time() < deadline:
        remaining_ms = max(1, int((deadline - time()) * 1000))
        try:
            raw = transport.read()
        except Exception as e:
            from ..errors import TransportError
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
            # Register 0xB5 replies also need the sub-register to match
            if is_receiver_register and request_id == 0x83B5:
                if rdata[2:3] == params_bytes[:1]:
                    return rdata[2:]  # strip (sub_id, reg); return from sub_reg onward
                continue  # sub-register mismatch — not our reply
            return rdata[2:]

    log.debug("Timeout (%.1fs) on request 0x%04X from device 0x%02X", timeout, request_id, devnumber)
    return None


# ── HID++ 2.0 feature operations ─────────────────────────────────────────────

def resolve_feature_index(
        transport: HIDTransport,
        devnumber: int,
        feature_code: int,
        long: bool = False,
) -> int | None:
    """Look up the feature table index for *feature_code* on the given device.

    Sends a ROOT (0x0000) GetFeature request.
    Returns the feature index (1-255), or None if not supported.
    """
    # ROOT feature is at index 0; GetFeature is function 0x00
    request_id = (FEATURE_ROOT << 8) | 0x00
    reply = request(
        transport, devnumber, request_id,
        feature_code >> 8, feature_code & 0xFF, 0x00,
        long=long, timeout=2.0,
    )
    if reply and reply[0] != 0x00:
        return reply[0]
    return None


def get_change_host_info(
        transport: HIDTransport,
        devnumber: int,
        feature_idx: int,
        long: bool = False,
) -> tuple[int, int] | None:
    """Return (num_hosts, current_host) for the given device. Returns None on failure."""
    request_id = (feature_idx << 8) | (CHANGE_HOST_FN_GET & 0xF0)
    reply = request(transport, devnumber, request_id, long=long, timeout=2.0)
    if reply and len(reply) >= 2:
        return reply[0], reply[1]
    return None


def send_change_host(
        transport: HIDTransport,
        devnumber: int,
        feature_idx: int,
        target_host: int,
        long: bool = False,
) -> None:
    """Switch *devnumber* to *target_host* (0-based). Fire-and-forget — no reply expected."""
    request_id = ((feature_idx << 8) | (CHANGE_HOST_FN_SET & 0xF0) | SW_ID)
    params = struct.pack("B", target_host)
    msg = _build_msg(devnumber, request_id, params, long)
    if log.isEnabledFor(logging.DEBUG):
        log.debug("send_change_host -> dev=0x%02X host=%d [%s]", devnumber, target_host, msg.hex())
    try:
        transport.write(msg)
    except Exception as e:
        from ..errors import TransportError
        raise TransportError(f"send_change_host write failed: {e}") from e


# ── HID++ 1.0 register access ─────────────────────────────────────────────────

def read_pairing_wpid(transport: HIDTransport, slot: int, receiver_kind: str) -> int | None:
    """Read the wireless PID of the device in *slot* (1-6) from a receiver.

    Uses HID++ 1.0 register 0x2B5 (RECEIVER_INFO).
    Byte layout differs between Bolt and Unifying:
      - Unifying: pair_info[3:5]           → wpid bytes (big-endian)
      - Bolt:     pair_info[3:4]+[2:3]     → wpid bytes (different ordering)

    Returns the wpid as an int (e.g. 0x408A), or None if the slot is empty.
    """
    if receiver_kind == "bolt":
        sub_reg = REG_PAIRING_INFO_BOLT + slot
    else:
        sub_reg = REG_PAIRING_INFO_UNIFYING + (slot - 1)

    # request_id for long register read: 0x8100 | (0x2B5 & 0x2FF) = 0x83B5
    register_id = 0x8100 | (REG_RECEIVER_INFO & 0x2FF)

    pair_info = request(
        transport, DEVICE_RECEIVER, register_id,
        sub_reg, 0x00, 0x00,
        timeout=1.0,
    )
    if not pair_info or len(pair_info) < 5:
        return None

    # pair_info[0] = sub_reg echo, pair_info[1..] = data bytes
    if receiver_kind == "bolt":
        # Bolt byte order: pair_info[3] then pair_info[2]
        wpid_bytes = bytes([pair_info[3], pair_info[2]])
    else:
        # Unifying byte order: pair_info[3], pair_info[4]
        wpid_bytes = pair_info[3:5]

    wpid = int(wpid_bytes.hex(), 16)
    return wpid if wpid != 0 else None


def set_cid_divert(
        transport: HIDTransport,
        devnumber: int,
        feat_idx: int,
        cid: int,
        diverted: bool,
        long: bool = False,
) -> bool:
    """Set or clear the temporary DIVERTED flag for *cid* via setCidReporting (fn 0x30).

    Returns True if the device replied (success), False on timeout/error.
    Payload layout: CID (2 bytes BE) + bfield (1 byte) + remap (2 bytes BE, always 0).
    """
    bfield = 0
    if diverted:
        flags = [MAP_FLAG_DIVERTED, MAP_FLAG_PERSISTENTLY_DIVERTED]
        for flag in flags:
            bfield |= flag
            bfield |= flag << 1
    params = struct.pack("!HBH", cid, bfield, 0)
    reply = request(transport, devnumber, (feat_idx << 8) | 0x30, params, long=long, timeout=2.0)
    return reply is not None


# ── Notification / message parsing ────────────────────────────────────────────

@dataclass
class FeatureEvent:
    """A HID++ 2.0 feature notification (unsolicited event from device)."""
    devnumber: int
    feature_idx: int  # = sub_id byte; matches the feature's resolved index
    function: int  # upper nibble of address byte (event function code)
    data: bytes  # payload starting at byte 4 of the raw message


@dataclass
class HostChangeEvent:
    """Diverted Easy-Switch event from device."""
    devnumber: int
    target_host: int  # device cid


def parse_message(divert_feat_idx: int, raw: bytes) -> FeatureEvent | HostChangeEvent | None:
    """Parse a raw HID++ packet into a structured event, or None if irrelevant."""
    if not raw or len(raw) < 4:
        return None

    log.debug("Attempt to parse raw data=: %s", raw)

    report_id = raw[0]
    devnumber = raw[1]
    sub_id = raw[2]
    address = raw[3]
    data = raw[4:]

    if (
            report_id == REPORT_LONG
            and address == 0x00
            and divert_feat_idx == sub_id
            and data[1] in HOST_SWITCH_CIDS.keys()
    ):
        return HostChangeEvent(devnumber, HOST_SWITCH_CIDS[data[1]])

    if (
            report_id in (REPORT_SHORT, REPORT_LONG)
            and sub_id < 0x80
            and (address & 0x0F) == 0x00
            and not (sub_id == 0x00 and address == 0x00)
    ):
        return FeatureEvent(devnumber, sub_id, address & 0xF0, data)

    return None
