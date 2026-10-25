"""Unit tests for HID++ message building in protocol.py."""

from __future__ import annotations

from cleverswitch.hidpp.constants import MSG_LONG_LEN, REPORT_LONG
from cleverswitch.hidpp.protocol import build_msg, pack_params

# ── pack_params ───────────────────────────────────────────────────────────────


def test_pack_params_returns_empty_bytes_for_no_params():
    assert pack_params(()) == b""


def test_pack_params_packs_single_int_as_one_byte():
    assert pack_params((5,)) == b"\x05"


def test_pack_params_passes_bytes_through_unchanged():
    assert pack_params((b"\xaa\xbb",)) == b"\xaa\xbb"


def test_pack_params_concatenates_mixed_int_and_bytes():
    params = (0xFF, b"\x01\x02")
    result = pack_params(params)
    assert result == b"\xff\x01\x02"


# ── build_msg ─────────────────────────────────────────────────────────────────


def test_build_msg_always_produces_20_byte_long_message():
    msg = build_msg(devnumber=1, request_id=0x0010, params=b"\x01")
    assert len(msg) == MSG_LONG_LEN
    assert msg[0] == REPORT_LONG
    assert msg[1] == 1


def test_build_msg_pads_small_payload_to_long():
    msg = build_msg(devnumber=2, request_id=0x0010, params=b"")
    assert len(msg) == MSG_LONG_LEN
    assert msg[0] == REPORT_LONG
    assert msg[1] == 2


def test_build_msg_embeds_request_id_big_endian_at_bytes_2_and_3():
    request_id = 0x1234
    msg = build_msg(devnumber=1, request_id=request_id, params=b"")
    assert msg[2] == 0x12
    assert msg[3] == 0x34
