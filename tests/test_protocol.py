"""Unit tests for HID++ protocol byte-manipulation functions.
#
Covers the pure, hardware-free layer of protocol.py:
  - _pack_params         — packing request parameters into bytes
  - _build_msg           — assembling short vs. long HID++ messages
  - _is_relevant         — filtering raw reads by report-ID and length
  - parse_message        — parsing raw packets into structured events
  - request              — request/reply with FakeTransport
  - resolve_feature_index, get_change_host_info, send_change_host,
    read_pairing_wpid, set_cid_divert
"""
#
from __future__ import annotations
#
import struct
#
import pytest
#
from cleverswitch.errors import TransportError
from cleverswitch.hidpp.constants import (
    DEVICE_RECEIVER,
    HOST_SWITCH_CIDS,
    MSG_DJ_LEN,
    MSG_LONG_LEN,
    MSG_SHORT_LEN,
    REPORT_DJ,
    REPORT_LONG,
    REPORT_SHORT,
    SW_ID,
)
from cleverswitch.hidpp.protocol import (
    FeatureEvent,
    HostChangeEvent,
    _build_msg,
    _is_relevant,
    _pack_params,
    get_change_host_info,
    get_device_name,
    parse_message,
    read_pairing_wpid,
    request,
    resolve_feature_index,
    send_change_host,
    set_cid_divert,
)
#
#
# ── Helpers ────────────────────────────────────────────────────────────────────
#
#
def _long_msg(devnumber: int, sub_id: int, address: int, data: bytes) -> bytes:
    """Build a 20-byte REPORT_LONG packet as the device would send it."""
    payload = bytes([sub_id, address]) + data
    return struct.pack("!BB18s", REPORT_LONG, devnumber, payload)
#
#
# ── _pack_params ───────────────────────────────────────────────────────────────
#
#
def test_pack_params_returns_empty_bytes_for_no_params():
    # Arrange / Act / Assert
    assert _pack_params(()) == b""
#
#
def test_pack_params_packs_single_int_as_one_byte():
    assert _pack_params((5,)) == b"\x05"
#
#
def test_pack_params_passes_bytes_through_unchanged():
    assert _pack_params((b"\xAA\xBB",)) == b"\xAA\xBB"
#
#
def test_pack_params_concatenates_mixed_int_and_bytes():
    # Arrange
    params = (0xFF, b"\x01\x02")
    # Act
    result = _pack_params(params)
    # Assert
    assert result == b"\xFF\x01\x02"
#
#
# ── _build_msg ─────────────────────────────────────────────────────────────────
#
#
def test_build_msg_produces_7_byte_short_message_for_small_payload():
    msg = _build_msg(devnumber=1, request_id=0x0010, params=b"\x01")
    assert len(msg) == MSG_SHORT_LEN
    assert msg[0] == REPORT_SHORT
    assert msg[1] == 1
#
#
def test_build_msg_produces_20_byte_long_message_when_forced():
    msg = _build_msg(devnumber=2, request_id=0x0010, params=b"\x01", long=True)
    assert len(msg) == MSG_LONG_LEN
    assert msg[0] == REPORT_LONG
    assert msg[1] == 2
#
#
def test_build_msg_promotes_to_long_when_payload_exceeds_short_limit():
    # request_id (2 bytes) + 4 bytes params = 6 bytes > MSG_SHORT_LEN - 2 = 5
    msg = _build_msg(devnumber=1, request_id=0x0010, params=b"\x01\x02\x03\x04")
    assert len(msg) == MSG_LONG_LEN
    assert msg[0] == REPORT_LONG
#
#
def test_build_msg_embeds_request_id_big_endian_at_bytes_2_and_3():
    # Arrange
    request_id = 0x1234
    # Act
    msg = _build_msg(devnumber=1, request_id=request_id, params=b"")
    # Assert: bytes 2-3 of a short message carry the big-endian request_id
    assert msg[2] == 0x12
    assert msg[3] == 0x34
#
#
# ── _is_relevant ──────────────────────────────────────────────────────────────
#
#
def test_is_relevant_returns_false_for_empty_bytes():
    assert _is_relevant(b"") is False
#
#
def test_is_relevant_returns_false_when_message_is_too_short():
    assert _is_relevant(b"\x10\x01") is False
#
#
def test_is_relevant_returns_false_for_unknown_report_id():
    # report_id=0x00 is not in _MSG_LENGTHS
    assert _is_relevant(bytes(7)) is False
#
#
def test_is_relevant_returns_true_for_valid_short_message():
    msg = bytes([REPORT_SHORT]) + bytes(MSG_SHORT_LEN - 1)
    assert _is_relevant(msg) is True
#
#
def test_is_relevant_returns_true_for_valid_long_message():
    msg = bytes([REPORT_LONG]) + bytes(MSG_LONG_LEN - 1)
    assert _is_relevant(msg) is True
#
#
def test_is_relevant_returns_true_for_valid_dj_message():
    msg = bytes([REPORT_DJ]) + bytes(MSG_DJ_LEN - 1)
    assert _is_relevant(msg) is True
#
#
def test_is_relevant_returns_false_when_length_mismatches_report_id():
    # REPORT_SHORT expects exactly MSG_SHORT_LEN bytes; 20 bytes is wrong
    msg = bytes([REPORT_SHORT]) + bytes(MSG_LONG_LEN - 1)
    assert _is_relevant(msg) is False
#
#
# ── parse_message ─────────────────────────────────────────────────────────────
#
#
DIVERT_FEAT_IDX = 5  # arbitrary feature index used throughout these tests
#
#
def test_parse_message_returns_none_for_empty_bytes():
    assert parse_message(DIVERT_FEAT_IDX, b"") is None
#
#
def test_parse_message_returns_none_for_message_shorter_than_4_bytes():
    assert parse_message(DIVERT_FEAT_IDX, b"\x11\x01\x05") is None
#
#
@pytest.mark.parametrize(
    "cid_byte, expected_host",
    [
        (0xD1, HOST_SWITCH_CIDS[0x00D1]),  # host 0
        (0xD2, HOST_SWITCH_CIDS[0x00D2]),  # host 1
        (0xD3, HOST_SWITCH_CIDS[0x00D3]),  # host 2
    ],
)
def test_parse_message_returns_host_change_event_for_each_easy_switch_cid(cid_byte, expected_host):
    # Arrange: raw[5] (data[1]) carries the CID byte matched against HOST_SWITCH_CIDS
    raw = _long_msg(
        devnumber=1,
        sub_id=DIVERT_FEAT_IDX,
        address=0x00,
        data=bytes([0x00, cid_byte]) + bytes(14),
    )
    # Act
    event = parse_message(DIVERT_FEAT_IDX, raw)
    # Assert
    assert isinstance(event, HostChangeEvent)
    assert event.devnumber == 1
    assert event.target_host == expected_host
#
#
def test_parse_message_does_not_return_host_change_event_when_cid_is_unknown():
    # Unknown CID → HostChangeEvent condition fails → falls through to FeatureEvent
    raw = _long_msg(
        devnumber=1,
        sub_id=DIVERT_FEAT_IDX,
        address=0x00,
        data=bytes([0x00, 0xAA]) + bytes(14),
    )
    event = parse_message(DIVERT_FEAT_IDX, raw)
    assert not isinstance(event, HostChangeEvent)
#
#
def test_parse_message_returns_none_when_address_byte_is_nonzero_for_host_change():
    # address must be 0x00 for a HostChangeEvent
    raw = _long_msg(
        devnumber=1,
        sub_id=DIVERT_FEAT_IDX,
        address=0x10,
        data=bytes([0x00, 0xD1]) + bytes(14),
    )
    # Should not be a HostChangeEvent; may or may not be a FeatureEvent
    event = parse_message(DIVERT_FEAT_IDX, raw)
    assert not isinstance(event, HostChangeEvent)
#
#
def test_parse_message_returns_feature_event_for_valid_short_message():
    # Arrange
    raw = bytes([REPORT_SHORT, 1, 0x05, 0x10, 0xAA, 0xBB, 0xCC])
    # Act
    event = parse_message(DIVERT_FEAT_IDX, raw)
    # Assert
    assert isinstance(event, FeatureEvent)
    assert event.devnumber == 1
    assert event.feature_idx == 0x05
    assert event.function == 0x10  # address & 0xF0
    assert event.data == bytes([0xAA, 0xBB, 0xCC])
#
#
def test_parse_message_returns_none_when_sub_id_is_zero_and_address_is_zero():
    # Explicitly excluded from FeatureEvent parsing
    raw = bytes([REPORT_SHORT, 1, 0x00, 0x00, 0x00, 0x00, 0x00])
    assert parse_message(DIVERT_FEAT_IDX, raw) is None
#
#
def test_parse_message_returns_none_when_address_low_nibble_is_nonzero():
    # address & 0x0F != 0 → not a FeatureEvent
    raw = bytes([REPORT_SHORT, 1, 0x05, 0x01, 0x00, 0x00, 0x00])
    assert parse_message(DIVERT_FEAT_IDX, raw) is None
#
#
def test_parse_message_returns_none_for_notification_sub_id_above_0x80():
    # sub_id >= 0x80 marks a HID++ 1.0/2.0 error or system message
    raw = bytes([REPORT_SHORT, 1, 0x8F, 0x00, 0x00, 0x00, 0x00])
    assert parse_message(DIVERT_FEAT_IDX, raw) is None
#
#
# ── request() ─────────────────────────────────────────────────────────────────
#
#
def _make_short_reply(devnumber: int, request_id: int, payload: bytes = b"\x00\x00\x00") -> bytes:
    """Build a 7-byte REPORT_SHORT reply whose rdata[:2] matches request_id."""
    return struct.pack("!BB", REPORT_SHORT, devnumber) + struct.pack("!H", request_id) + payload[:3]
#
#
def test_request_returns_payload_on_successful_short_reply(make_fake_transport):
    # Arrange: devnumber=1, request_id=0x0100 → after SW_ID: 0x0108
    effective_id = (0x0100 & 0xFFF0) | SW_ID  # 0x0108
    reply = _make_short_reply(1, effective_id, b"\xAA\xBB\xCC")
    t = make_fake_transport(responses=[reply])
    # Act
    result = request(t, devnumber=1, request_id=0x0100)
    # Assert: payload after the 2-byte request_id echo
    assert result == b"\xAA\xBB\xCC"
#
#
def test_request_writes_message_to_transport(make_fake_transport):
    effective_id = (0x0100 & 0xFFF0) | SW_ID
    reply = _make_short_reply(1, effective_id, b"\x00\x00\x00")
    t = make_fake_transport(responses=[reply])
    request(t, devnumber=1, request_id=0x0100)
    assert len(t.written) == 1
#
#
def test_request_returns_none_on_timeout(mocker, fake_transport):
    # Make deadline expire before the first read
    mocker.patch("cleverswitch.hidpp.protocol.time", side_effect=[0.0, 100.0])
    result = request(fake_transport, devnumber=1, request_id=0x0100)
    assert result is None
#
#
def test_request_raises_transport_error_on_write_failure(mocker, fake_transport):
    mocker.patch.object(fake_transport, "write", side_effect=OSError("device gone"))
    with pytest.raises(TransportError, match="write failed"):
        request(fake_transport, devnumber=1, request_id=0x0100)
#
#
def test_request_raises_transport_error_on_read_failure(mocker, fake_transport):
    # Allow write to succeed; make deadline valid then raise on read
    mocker.patch("cleverswitch.hidpp.protocol.time", side_effect=[0.0, 1.0])
    mocker.patch.object(fake_transport, "read", side_effect=OSError("read error"))
    with pytest.raises(TransportError, match="read failed"):
        request(fake_transport, devnumber=1, request_id=0x0100)
#
#
def test_request_returns_none_on_hidpp1_error_reply(make_fake_transport):
    # Arrange: HID++ 1.0 error reply — sub_id=0x8F, next 2 bytes echo our request_id
    effective_id = (0x0100 & 0xFFF0) | SW_ID  # 0x0108
    # Reply: [REPORT_SHORT, devnumber, 0x8F, id_hi, id_lo, error_code, 0x00]
    hi, lo = (effective_id >> 8) & 0xFF, effective_id & 0xFF
    reply = bytes([REPORT_SHORT, 1, 0x8F, hi, lo, 0x05, 0x00])
    t = make_fake_transport(responses=[reply])
    result = request(t, devnumber=1, request_id=0x0100)
    assert result is None
#
#
def test_request_returns_none_on_hidpp2_error_reply(make_fake_transport):
    # Arrange: HID++ 2.0 error reply — sub_id=0xFF, next 2 bytes echo our request_id
    effective_id = (0x0100 & 0xFFF0) | SW_ID
    hi, lo = (effective_id >> 8) & 0xFF, effective_id & 0xFF
    reply = bytes([REPORT_SHORT, 1, 0xFF, hi, lo, 0x09, 0x00])
    t = make_fake_transport(responses=[reply])
    result = request(t, devnumber=1, request_id=0x0100)
    assert result is None
#
#
def test_request_skips_reply_from_wrong_device_and_returns_none_on_timeout(mocker, make_fake_transport):
    # Wrong devnumber reply → skipped; transport exhausted → timeout
    effective_id = (0x0100 & 0xFFF0) | SW_ID
    wrong_reply = _make_short_reply(99, effective_id, b"\x00\x00\x00")
    t = make_fake_transport(responses=[wrong_reply])
    # Make time expire after the wrong reply is consumed
    mocker.patch("cleverswitch.hidpp.protocol.time", side_effect=[0.0, 0.5, 0.5, 100.0])
    result = request(t, devnumber=1, request_id=0x0100)
    assert result is None
#
#
def test_request_does_not_add_sw_id_for_receiver_register(make_fake_transport):
    # devnumber=0xFF, request_id=0x8100 → is_receiver_register=True → SW_ID NOT added
    reply = _make_short_reply(DEVICE_RECEIVER, 0x8100, b"\x00\x00\x00")
    t = make_fake_transport(responses=[reply])
    request(t, devnumber=DEVICE_RECEIVER, request_id=0x8100)
    # Verify SW_ID was not added: bytes 2-3 of written message should be 0x81, 0x00
    assert t.written[0][2] == 0x81
    assert t.written[0][3] == 0x00
#
#
# ── resolve_feature_index() ──────────────────────────────────────────────────
#
#
def test_resolve_feature_index_returns_index_when_feature_is_supported(mocker, fake_transport):
    mocker.patch("cleverswitch.hidpp.protocol.request", return_value=b"\x05\x00\x00")
    result = resolve_feature_index(fake_transport, devnumber=1, feature_code=0x1814)
    assert result == 5
#
#
def test_resolve_feature_index_returns_none_when_request_fails(mocker, fake_transport):
    mocker.patch("cleverswitch.hidpp.protocol.request", return_value=None)
    result = resolve_feature_index(fake_transport, devnumber=1, feature_code=0x1814)
    assert result is None
#
#
def test_resolve_feature_index_returns_none_when_first_reply_byte_is_zero(mocker, fake_transport):
    mocker.patch("cleverswitch.hidpp.protocol.request", return_value=b"\x00\x00\x00")
    result = resolve_feature_index(fake_transport, devnumber=1, feature_code=0x1814)
    assert result is None
#
#
# ── get_change_host_info() ────────────────────────────────────────────────────
#
#
def test_get_change_host_info_returns_num_hosts_and_current_host(mocker, fake_transport):
    mocker.patch("cleverswitch.hidpp.protocol.request", return_value=b"\x03\x01")
    result = get_change_host_info(fake_transport, devnumber=1, feature_idx=4)
    assert result == (3, 1)
#
#
def test_get_change_host_info_returns_none_when_request_fails(mocker, fake_transport):
    mocker.patch("cleverswitch.hidpp.protocol.request", return_value=None)
    result = get_change_host_info(fake_transport, devnumber=1, feature_idx=4)
    assert result is None
#
#
# ── send_change_host() ────────────────────────────────────────────────────────
#
#
def test_send_change_host_writes_message_to_transport(fake_transport):
    send_change_host(fake_transport, devnumber=1, feature_idx=4, target_host=2)
    assert len(fake_transport.written) == 1
#
#
def test_send_change_host_raises_transport_error_on_write_failure(mocker, fake_transport):
    mocker.patch.object(fake_transport, "write", side_effect=OSError("gone"))
    with pytest.raises(TransportError, match="send_change_host write failed"):
        send_change_host(fake_transport, devnumber=1, feature_idx=4, target_host=2)
#
#
# ── read_pairing_wpid() ───────────────────────────────────────────────────────
#
#
def test_read_pairing_wpid_returns_wpid_for_bolt_receiver(mocker, fake_transport):
    # Bolt byte order: pair_info[3] then pair_info[2] → wpid
    # pair_info[0] = sub_reg echo, pair_info[1..] = data
    # pair_info[2]=0x8A, pair_info[3]=0x40 → wpid bytes = [0x40, 0x8A] → 0x408A
    pair_info = bytes([0x50, 0x00, 0x8A, 0x40, 0x00])
    mocker.patch("cleverswitch.hidpp.protocol.request", return_value=pair_info)
    result = read_pairing_wpid(fake_transport, slot=1, receiver_kind="bolt")
    assert result == 0x408A
#
#
def test_read_pairing_wpid_returns_wpid_for_unifying_receiver(mocker, fake_transport):
    # Unifying byte order: pair_info[3], pair_info[4] → wpid
    # pair_info[3]=0x40, pair_info[4]=0x82 → wpid = 0x4082
    pair_info = bytes([0x20, 0x00, 0x00, 0x40, 0x82])
    mocker.patch("cleverswitch.hidpp.protocol.request", return_value=pair_info)
    result = read_pairing_wpid(fake_transport, slot=1, receiver_kind="unifying")
    assert result == 0x4082
#
#
def test_read_pairing_wpid_returns_none_when_pair_info_is_none(mocker, fake_transport):
    mocker.patch("cleverswitch.hidpp.protocol.request", return_value=None)
    result = read_pairing_wpid(fake_transport, slot=1, receiver_kind="bolt")
    assert result is None
#
#
def test_read_pairing_wpid_returns_none_when_wpid_is_zero(mocker, fake_transport):
    # All-zero pair_info → wpid=0 → returns None (empty slot)
    pair_info = bytes([0x50, 0x00, 0x00, 0x00, 0x00])
    mocker.patch("cleverswitch.hidpp.protocol.request", return_value=pair_info)
    result = read_pairing_wpid(fake_transport, slot=1, receiver_kind="bolt")
    assert result is None
#
#
# ── set_cid_divert() ──────────────────────────────────────────────────────────
#
#
def test_set_cid_divert_returns_true_when_request_succeeds(mocker, fake_transport):
    mocker.patch("cleverswitch.hidpp.protocol.request", return_value=b"\x01\x02\x03")
    result = set_cid_divert(fake_transport, devnumber=1, feat_idx=3, cid=0x00D1, diverted=True)
    assert result is True
#
#
def test_set_cid_divert_returns_false_when_request_fails(mocker, fake_transport):
    mocker.patch("cleverswitch.hidpp.protocol.request", return_value=None)
    result = set_cid_divert(fake_transport, devnumber=1, feat_idx=3, cid=0x00D1, diverted=True)
    assert result is False
#
#
# ── get_device_name() ─────────────────────────────────────────────────────────
#
#
def test_get_device_name_returns_name_from_single_chunk(mocker, fake_transport):
    # Arrange: nameCount=7, getDeviceName returns all 7 chars in one long reply
    mocker.patch(
        "cleverswitch.hidpp.protocol.request",
        side_effect=[
            b"\x07",                          # getDeviceNameCount → nameLen=7
            b"MX Keys" + b"\x00" * 9,         # getDeviceName(0) → 16-byte chunk
        ],
    )
    result = get_device_name(fake_transport, devnumber=1, feat_idx=2)
    assert result == "MX Keys"
#
#
def test_get_device_name_assembles_name_from_multiple_chunks(mocker, fake_transport):
    # Arrange: nameCount=11, device returns 3 chars per short-message call
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
#
#
def test_get_device_name_returns_none_when_namecount_request_fails(mocker, fake_transport):
    mocker.patch("cleverswitch.hidpp.protocol.request", return_value=None)
    assert get_device_name(fake_transport, devnumber=1, feat_idx=2) is None
#
#
def test_get_device_name_returns_none_when_namecount_is_zero(mocker, fake_transport):
    mocker.patch("cleverswitch.hidpp.protocol.request", return_value=b"\x00")
    assert get_device_name(fake_transport, devnumber=1, feat_idx=2) is None
#
#
def test_get_device_name_returns_partial_name_when_chunk_request_fails(mocker, fake_transport):
    # First chunk returns 3 chars, second call fails
    mocker.patch(
        "cleverswitch.hidpp.protocol.request",
        side_effect=[
            b"\x07",    # nameLen=7
            b"MX ",     # chars 0-2
            None,       # chars 3+ → failure
        ],
    )
    # Partial result is still returned
    result = get_device_name(fake_transport, devnumber=1, feat_idx=2)
    assert result == "MX "
