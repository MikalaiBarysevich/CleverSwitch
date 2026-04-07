"""Unit tests for parser/parser.py — raw HID++ bytes → Event."""

from __future__ import annotations

import struct

from cleverswitch.event.device_connected_event import DeviceConnectedEvent
from cleverswitch.event.external_undivert_event import ExternalUndivertEvent
from cleverswitch.event.hidpp_error_event import HidppErrorEvent
from cleverswitch.event.hidpp_notification_event import HidppNotificationEvent
from cleverswitch.event.hidpp_response_event import HidppResponseEvent
from cleverswitch.hidpp.constants import (
    BOLT_PID,
    GET_LONG_REGISTER_RSP,
    HOST_SWITCH_CIDS,
    MAP_FLAG_DIVERTED,
    REGISTER_PAIRING_INFO,
    REPORT_LONG,
    REPORT_SHORT,
    SW_ID,
)
from cleverswitch.parser.parser import parse

PID = BOLT_PID


def _long_msg(slot: int, feature_id: int, fn_sw: int, data: bytes = b"") -> bytes:
    payload = bytes([feature_id, fn_sw]) + data
    return struct.pack("!BB18s", REPORT_LONG, slot, payload)


def _short_msg(slot: int, sub_id: int, data: bytes = b"") -> bytes:
    payload = bytes([sub_id]) + data
    return struct.pack("!BB5s", REPORT_SHORT, slot, payload)


# ── Device Connection (0x41) ─────────────────────────────────────────────────


def test_parse_device_connection_link_established():
    # 0x10 slot 0x41 0x00 r1=0x01(type=1,link=yes) wpid_lo wpid_hi
    raw = bytes([REPORT_SHORT, 0x01, 0x41, 0x00, 0x01, 0x7B, 0x40])
    event = parse(PID, raw)
    assert isinstance(event, DeviceConnectedEvent)
    assert event.slot == 1
    assert event.pid == PID
    assert event.link_established is True
    assert event.wpid == 0x407B
    assert event.device_type == 1


def test_parse_device_connection_disconnected():
    # r1 bit 6 set = disconnected
    raw = bytes([REPORT_SHORT, 0x02, 0x41, 0x00, 0x40, 0x7B, 0x40])
    event = parse(PID, raw)
    assert isinstance(event, DeviceConnectedEvent)
    assert event.link_established is False


def test_parse_device_connection_type_zero_becomes_none():
    raw = bytes([REPORT_SHORT, 0x01, 0x41, 0x00, 0x00, 0x7B, 0x40])
    event = parse(PID, raw)
    assert isinstance(event, DeviceConnectedEvent)
    assert event.device_type is None


# ── HID++ 1.0 error (0x8F) ──────────────────────────────────────────────────


def test_parse_hidpp1_error():
    raw = bytes([REPORT_SHORT, 0x01, 0x8F, 0x08, 0x00, 0x05, 0x00])
    event = parse(PID, raw)
    assert isinstance(event, HidppErrorEvent)
    assert event.sw_id == 0x08
    assert event.error_code == 0x05


# ── HID++ 2.0 error (feature=0xFF) ───────────────────────────────────────────


def test_parse_hidpp2_error():
    raw = _long_msg(slot=1, feature_id=0xFF, fn_sw=0x08, data=bytes([0x00, 0x09]) + bytes(14))
    event = parse(PID, raw)
    assert isinstance(event, HidppErrorEvent)
    assert event.error_code == 0x09


# ── HID++ 2.0 response (sw_id with bit 3 set) ───────────────────────────────


def test_parse_response():
    # fn=1, sw_id=0x08 → fn_sw = 0x18
    raw = _long_msg(slot=1, feature_id=5, fn_sw=0x18, data=bytes(16))
    event = parse(PID, raw)
    assert isinstance(event, HidppResponseEvent)
    assert event.feature_index == 5
    assert event.function == 1
    assert event.sw_id == SW_ID


# ── HID++ 2.0 notification (sw_id == 0) ─────────────────────────────────────


def test_parse_notification():
    # fn=0, sw_id=0 → fn_sw = 0x00
    raw = _long_msg(slot=1, feature_id=5, fn_sw=0x00, data=bytes(16))
    event = parse(PID, raw)
    assert isinstance(event, HidppNotificationEvent)
    assert event.feature_index == 5
    assert event.function == 0


# ── External undivert (fn=3, ES CID, divert cleared) ────────────────────────


def test_parse_external_undivert():
    # fn=3, sw_id=0x02 → fn_sw = 0x32; CID=0x00D1; bfield: valid bit set, divert cleared
    bfield = MAP_FLAG_DIVERTED << 1  # valid=1, divert=0
    data = bytes([0x00, 0xD1, bfield]) + bytes(13)
    raw = _long_msg(slot=1, feature_id=5, fn_sw=0x32, data=data)
    event = parse(PID, raw)
    assert isinstance(event, ExternalUndivertEvent)
    assert event.cid == 0x00D1
    assert event.feature_index == 5


def test_parse_external_undivert_ignored_for_non_es_cid():
    bfield = MAP_FLAG_DIVERTED << 1
    data = bytes([0x00, 0xAA, bfield]) + bytes(13)
    raw = _long_msg(slot=1, feature_id=5, fn_sw=0x32, data=data)
    assert parse(PID, raw) is None


def test_parse_external_undivert_ignored_when_divert_set():
    bfield = (MAP_FLAG_DIVERTED << 1) | MAP_FLAG_DIVERTED  # valid=1, divert=1
    data = bytes([0x00, 0xD1, bfield]) + bytes(13)
    raw = _long_msg(slot=1, feature_id=5, fn_sw=0x32, data=data)
    assert parse(PID, raw) is None


# ── Unknown / None ───────────────────────────────────────────────────────────


# ── 0xB5 Pairing Information (GET_LONG_REGISTER_RSP) ────────────────────────


def _b5_response(sub_page: int, wpid_msb: int, wpid_lsb: int, device_type: int) -> bytes:
    raw = bytearray(20)
    raw[0] = REPORT_LONG
    raw[1] = 0xFF
    raw[2] = GET_LONG_REGISTER_RSP
    raw[3] = REGISTER_PAIRING_INFO
    raw[4] = sub_page
    raw[7] = wpid_msb
    raw[8] = wpid_lsb
    raw[11] = device_type
    return bytes(raw)


def test_parse_b5_slot1_keyboard():
    raw = _b5_response(sub_page=0x20, wpid_msb=0x40, wpid_lsb=0x7B, device_type=0x01)
    event = parse(PID, raw)
    assert isinstance(event, DeviceConnectedEvent)
    assert event.slot == 1
    assert event.wpid == 0x407B
    assert event.device_type == 1
    assert event.link_established is False


def test_parse_b5_slot6_mouse():
    raw = _b5_response(sub_page=0x25, wpid_msb=0x40, wpid_lsb=0x82, device_type=0x02)
    event = parse(PID, raw)
    assert isinstance(event, DeviceConnectedEvent)
    assert event.slot == 6
    assert event.wpid == 0x4082
    assert event.device_type == 2


def test_parse_b5_device_type_zero_becomes_none():
    raw = _b5_response(sub_page=0x21, wpid_msb=0x40, wpid_lsb=0x7B, device_type=0x00)
    event = parse(PID, raw)
    assert isinstance(event, DeviceConnectedEvent)
    assert event.device_type is None


def test_parse_b5_wpid_msb_first():
    """WPID byte order is MSB-first in 0xB5 (opposite of 0x41)."""
    raw = _b5_response(sub_page=0x20, wpid_msb=0xAB, wpid_lsb=0xCD, device_type=0x01)
    event = parse(PID, raw)
    assert event.wpid == 0xABCD


# ── Unknown / None ───────────────────────────────────────────────────────────


def test_parse_unknown_short_returns_none():
    raw = bytes([REPORT_SHORT, 1, 0x42, 0x00, 0x00, 0x00, 0x00])
    assert parse(PID, raw) is None


def test_parse_unknown_long_sw_id_returns_none():
    # fn=0, sw_id=0x02 (not 0, not bit3 set, not fn=3)
    raw = _long_msg(slot=1, feature_id=5, fn_sw=0x02, data=bytes(16))
    assert parse(PID, raw) is None
