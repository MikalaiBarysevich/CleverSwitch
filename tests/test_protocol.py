"""Unit tests for HID++ protocol byte-manipulation functions.

Covers the pure, hardware-free layer of protocol.py:
  - _pack_params         — packing request parameters into bytes
  - _build_msg           — assembling long HID++ messages
  - _is_relevant         — filtering raw reads by report-ID and length
  - request              — request/reply with FakeTransport
  - resolve_feature_index, send_change_host,
    set_cid_divert, get_device_name
"""

from __future__ import annotations

import struct

import pytest

from cleverswitch.errors import TransportError
from cleverswitch.hidpp.constants import (
    MSG_DJ_LEN,
    MSG_LONG_LEN,
    MSG_SHORT_LEN,
    REPORT_DJ,
    REPORT_LONG,
    REPORT_SHORT,
    SW_ID,
)
from cleverswitch.hidpp.protocol import (
    _build_msg,
    _is_relevant,
    _pack_params,
    get_device_name,
    get_device_type,
    request,
    resolve_feature_index,
    send_change_host,
    set_cid_divert,
)


# ── _pack_params ───────────────────────────────────────────────────────────────


def test_pack_params_returns_empty_bytes_for_no_params():
    assert _pack_params(()) == b""


def test_pack_params_packs_single_int_as_one_byte():
    assert _pack_params((5,)) == b"\x05"


def test_pack_params_passes_bytes_through_unchanged():
    assert _pack_params((b"\xAA\xBB",)) == b"\xAA\xBB"


def test_pack_params_concatenates_mixed_int_and_bytes():
    params = (0xFF, b"\x01\x02")
    result = _pack_params(params)
    assert result == b"\xFF\x01\x02"


# ── _build_msg ─────────────────────────────────────────────────────────────────


def test_build_msg_always_produces_20_byte_long_message():
    msg = _build_msg(devnumber=1, request_id=0x0010, params=b"\x01")
    assert len(msg) == MSG_LONG_LEN
    assert msg[0] == REPORT_LONG
    assert msg[1] == 1


def test_build_msg_pads_small_payload_to_long():
    msg = _build_msg(devnumber=2, request_id=0x0010, params=b"")
    assert len(msg) == MSG_LONG_LEN
    assert msg[0] == REPORT_LONG
    assert msg[1] == 2


def test_build_msg_embeds_request_id_big_endian_at_bytes_2_and_3():
    request_id = 0x1234
    msg = _build_msg(devnumber=1, request_id=request_id, params=b"")
    assert msg[2] == 0x12
    assert msg[3] == 0x34


# ── _is_relevant ──────────────────────────────────────────────────────────────


def test_is_relevant_returns_false_for_empty_bytes():
    assert _is_relevant(b"") is False


def test_is_relevant_returns_false_when_message_is_too_short():
    assert _is_relevant(b"\x10\x01") is False


def test_is_relevant_returns_false_for_unknown_report_id():
    assert _is_relevant(bytes(7)) is False


def test_is_relevant_returns_true_for_valid_short_message():
    msg = bytes([REPORT_SHORT]) + bytes(MSG_SHORT_LEN - 1)
    assert _is_relevant(msg) is True


def test_is_relevant_returns_true_for_valid_long_message():
    msg = bytes([REPORT_LONG]) + bytes(MSG_LONG_LEN - 1)
    assert _is_relevant(msg) is True


def test_is_relevant_returns_true_for_valid_dj_message():
    msg = bytes([REPORT_DJ]) + bytes(MSG_DJ_LEN - 1)
    assert _is_relevant(msg) is True


def test_is_relevant_returns_false_when_length_mismatches_report_id():
    msg = bytes([REPORT_SHORT]) + bytes(MSG_LONG_LEN - 1)
    assert _is_relevant(msg) is False


# ── request() ─────────────────────────────────────────────────────────────────


def _make_long_reply(devnumber: int, request_id: int, payload: bytes = b"\x00" * 16) -> bytes:
    """Build a 20-byte REPORT_LONG reply whose rdata[:2] matches request_id."""
    data = struct.pack("!H", request_id) + payload[:16]
    return struct.pack("!BB18s", REPORT_LONG, devnumber, data)


def test_request_returns_payload_on_successful_reply(make_fake_transport):
    effective_id = (0x0100 & 0xFFF0) | SW_ID  # 0x0108
    reply = _make_long_reply(1, effective_id, b"\xAA\xBB\xCC")
    t = make_fake_transport(responses=[reply])
    result = request(t, devnumber=1, request_id=0x0100)
    assert result[:3] == b"\xAA\xBB\xCC"


def test_request_writes_message_to_transport(make_fake_transport):
    effective_id = (0x0100 & 0xFFF0) | SW_ID
    reply = _make_long_reply(1, effective_id)
    t = make_fake_transport(responses=[reply])
    request(t, devnumber=1, request_id=0x0100)
    assert len(t.written) == 1


def test_request_returns_none_on_timeout(mocker, fake_transport):
    mocker.patch("cleverswitch.hidpp.protocol.time", side_effect=[0.0, 100.0])
    result = request(fake_transport, devnumber=1, request_id=0x0100)
    assert result is None


def test_request_raises_transport_error_on_write_failure(mocker, fake_transport):
    mocker.patch.object(fake_transport, "write", side_effect=OSError("device gone"))
    with pytest.raises(TransportError, match="write failed"):
        request(fake_transport, devnumber=1, request_id=0x0100)


def test_request_raises_transport_error_on_read_failure(mocker, fake_transport):
    # First time() call sets deadline, second allows loop entry, read then raises
    mocker.patch("cleverswitch.hidpp.protocol.time", side_effect=[0.0, 0.1, 100.0])
    mocker.patch.object(fake_transport, "read", side_effect=OSError("read error"))
    with pytest.raises(TransportError, match="read failed"):
        request(fake_transport, devnumber=1, request_id=0x0100)


def test_request_returns_none_on_hidpp1_error_reply(make_fake_transport):
    effective_id = (0x0100 & 0xFFF0) | SW_ID  # 0x0108
    hi, lo = (effective_id >> 8) & 0xFF, effective_id & 0xFF
    reply = bytes([REPORT_SHORT, 1, 0x8F, hi, lo, 0x05, 0x00])
    t = make_fake_transport(responses=[reply])
    result = request(t, devnumber=1, request_id=0x0100)
    assert result is None


def test_request_returns_none_on_hidpp2_error_reply(make_fake_transport):
    effective_id = (0x0100 & 0xFFF0) | SW_ID
    hi, lo = (effective_id >> 8) & 0xFF, effective_id & 0xFF
    reply = bytes([REPORT_SHORT, 1, 0xFF, hi, lo, 0x09, 0x00])
    t = make_fake_transport(responses=[reply])
    result = request(t, devnumber=1, request_id=0x0100)
    assert result is None


def test_request_skips_reply_from_wrong_device_and_returns_none_on_timeout(mocker, make_fake_transport):
    effective_id = (0x0100 & 0xFFF0) | SW_ID
    wrong_reply = _make_long_reply(99, effective_id)
    t = make_fake_transport(responses=[wrong_reply])
    mocker.patch("cleverswitch.hidpp.protocol.time", side_effect=[0.0, 0.5, 0.5, 100.0])
    result = request(t, devnumber=1, request_id=0x0100)
    assert result is None


# ── resolve_feature_index() ──────────────────────────────────────────────────


def test_resolve_feature_index_returns_index_when_feature_is_supported(mocker, fake_transport):
    mocker.patch("cleverswitch.hidpp.protocol.request", return_value=b"\x05\x00\x00")
    result = resolve_feature_index(fake_transport, devnumber=1, feature_code=0x1814)
    assert result == 5


def test_resolve_feature_index_returns_none_when_request_fails(mocker, fake_transport):
    mocker.patch("cleverswitch.hidpp.protocol.request", return_value=None)
    result = resolve_feature_index(fake_transport, devnumber=1, feature_code=0x1814)
    assert result is None


def test_resolve_feature_index_returns_none_when_first_reply_byte_is_zero(mocker, fake_transport):
    mocker.patch("cleverswitch.hidpp.protocol.request", return_value=b"\x00\x00\x00")
    result = resolve_feature_index(fake_transport, devnumber=1, feature_code=0x1814)
    assert result is None


# ── get_device_type() ─────────────────────────────────────────────────────────


def test_get_device_type_returns_type_byte(mocker, fake_transport):
    mocker.patch("cleverswitch.hidpp.protocol.request", return_value=b"\x03\x00")
    result = get_device_type(fake_transport, devnumber=1, feat_idx=2)
    assert result == 3


def test_get_device_type_returns_none_when_request_fails(mocker, fake_transport):
    mocker.patch("cleverswitch.hidpp.protocol.request", return_value=None)
    result = get_device_type(fake_transport, devnumber=1, feat_idx=2)
    assert result is None


# ── send_change_host() ────────────────────────────────────────────────────────


def test_send_change_host_writes_message_to_transport(fake_transport):
    send_change_host(fake_transport, devnumber=1, feature_idx=4, target_host=2)
    assert len(fake_transport.written) == 1


def test_send_change_host_raises_transport_error_on_write_failure(mocker, fake_transport):
    mocker.patch.object(fake_transport, "write", side_effect=OSError("gone"))
    with pytest.raises(TransportError, match="send_change_host write failed"):
        send_change_host(fake_transport, devnumber=1, feature_idx=4, target_host=2)



# ── set_cid_divert() ──────────────────────────────────────────────────────────


def test_set_cid_divert_writes_message_to_transport(fake_transport):
    set_cid_divert(fake_transport, devnumber=1, feat_idx=3, cid=0x00D1, diverted=True)
    assert len(fake_transport.written) == 1


def test_set_cid_divert_returns_none(fake_transport):
    result = set_cid_divert(fake_transport, devnumber=1, feat_idx=3, cid=0x00D1, diverted=True)
    assert result is None


def test_set_cid_divert_writes_message_when_diverted_false(fake_transport):
    set_cid_divert(fake_transport, devnumber=1, feat_idx=3, cid=0x00D1, diverted=False)
    assert len(fake_transport.written) == 1


# ── get_device_name() ─────────────────────────────────────────────────────────


def test_get_device_name_returns_name_from_single_chunk(mocker, fake_transport):
    mocker.patch(
        "cleverswitch.hidpp.protocol.request",
        side_effect=[
            b"\x07",                          # getDeviceNameCount → nameLen=7
            b"MX Keys" + b"\x00" * 9,         # getDeviceName(0) → 16-byte chunk
        ],
    )
    result = get_device_name(fake_transport, devnumber=1, feat_idx=2)
    assert result == "MX Keys"


def test_get_device_name_assembles_name_from_multiple_chunks(mocker, fake_transport):
    mocker.patch(
        "cleverswitch.hidpp.protocol.request",
        side_effect=[
            b"\x0b",        # getDeviceNameCount → nameLen=11 ("MX Master 3")
            b"MX ",         # getDeviceName(0)  → chars 0-2
            b"Mas",         # getDeviceName(3)  → chars 3-5
            b"ter",         # getDeviceName(6)  → chars 6-8
            b" 3\x00",      # getDeviceName(9)  → chars 9-10 + padding
        ],
    )
    result = get_device_name(fake_transport, devnumber=1, feat_idx=2)
    assert result == "MX Master 3"


def test_get_device_name_returns_none_when_namecount_request_fails(mocker, fake_transport):
    mocker.patch("cleverswitch.hidpp.protocol.request", return_value=None)
    assert get_device_name(fake_transport, devnumber=1, feat_idx=2) is None


def test_get_device_name_returns_none_when_namecount_is_zero(mocker, fake_transport):
    mocker.patch("cleverswitch.hidpp.protocol.request", return_value=b"\x00")
    assert get_device_name(fake_transport, devnumber=1, feat_idx=2) is None


def test_get_device_name_returns_partial_name_when_chunk_request_fails(mocker, fake_transport):
    mocker.patch(
        "cleverswitch.hidpp.protocol.request",
        side_effect=[
            b"\x07",    # nameLen=7
            b"MX ",     # chars 0-2
            None,       # chars 3+ → failure
        ],
    )
    result = get_device_name(fake_transport, devnumber=1, feat_idx=2)
    assert result == "MX "
