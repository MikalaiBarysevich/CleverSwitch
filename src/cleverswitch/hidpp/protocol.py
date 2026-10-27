"""HID++ message building."""

from __future__ import annotations

import struct

from .constants import REPORT_LONG


def pack_params(params: tuple) -> bytes:
    if not params:
        return b""
    parts = []
    for p in params:
        if isinstance(p, int):
            parts.append(struct.pack("B", p))
        else:
            parts.append(bytes(p))
    return b"".join(parts)


def build_msg(devnumber: int, request_id: int, params: bytes) -> bytes:
    """Assemble a complete HID++ long message (report 0x11, 20 bytes).

    Always uses long format — HID++ 2.0 responses are always long, and on
    Windows each report type is a separate HID collection. Sending long
    ensures request and response use the same collection handle.
    """
    data = struct.pack("!H", request_id) + params
    return struct.pack("!BB18s", REPORT_LONG, devnumber, data)
