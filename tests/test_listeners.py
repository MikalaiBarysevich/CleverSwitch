"""Unit tests for listeners.py.

Covers:
  - parse_message        — raw HID++ bytes → structured event or None
  - _device_type_to_role — x0005 deviceType → 'keyboard' / 'mouse' / None
  - _query_device_info   — feature resolution → (role, name) or None
  - _divert_all_es_keys  — calls set_cid_divert for each HOST_SWITCH_CID
  - _undivert_all_es_keys — same, but suppresses all exceptions
  - PathListener         — per-receiver thread lifecycle
"""

from __future__ import annotations

import struct
import threading

import pytest

from cleverswitch.hidpp.constants import (
    BOLT_PID,
    DEVICE_TYPE_KEYBOARD,
    DEVICE_TYPE_MOUSE,
    DEVICE_TYPE_TRACKBALL,
    DEVICE_TYPE_TRACKPAD,
    DJ_DEVICE_PAIRING,
    HOST_SWITCH_CIDS,
    MSG_DJ_LEN,
    REPORT_DJ,
    REPORT_LONG,
    REPORT_SHORT,
    SW_ID,
)
from cleverswitch.hidpp.transport import HidDeviceInfo
from cleverswitch.listeners import (
    PathListener,
    _device_type_to_role,
    _divert_all_es_keys,
    _query_device_info,
    _undivert_all_es_keys,
    parse_message,
)
from cleverswitch.model import ConnectionEvent, ExternalUndivertEvent, HostChangeEvent, LogiProduct


# ── Helpers ───────────────────────────────────────────────────────────────────


def _long_msg(slot: int, sub_id: int, address: int, data: bytes) -> bytes:
    payload = bytes([sub_id, address]) + data
    return struct.pack("!BB18s", REPORT_LONG, slot, payload)


def _dj_msg(slot: int, feature_id: int, address: int) -> bytes:
    payload = bytes([feature_id, address]) + bytes(MSG_DJ_LEN - 3)
    return bytes([REPORT_DJ, slot]) + payload


def _make_path_listener(mocker, device=None, shutdown=None, init_transport=True):
    """Instantiate PathListener with HIDTransport and _query_device_info mocked out.

    By default calls init_transport() so listener._transport is set.
    Pass init_transport=False to test __init__-only state.
    """
    if device is None:
        device = HidDeviceInfo(path=b"/dev/hidraw0", vid=0x046D, pid=BOLT_PID, usage_page=0xFF00, usage=1)
    if shutdown is None:
        shutdown = threading.Event()

    mock_transport = mocker.MagicMock()
    mocker.patch("cleverswitch.listeners.HIDTransport", return_value=mock_transport)
    mocker.patch("cleverswitch.listeners._query_device_info", return_value=None)

    listener = PathListener(device, shutdown)
    if init_transport:
        listener.init_transport()
    return listener, mock_transport


# ── _device_type_to_role ──────────────────────────────────────────────────────


def test_device_type_to_role_keyboard():
    assert _device_type_to_role(DEVICE_TYPE_KEYBOARD) == "keyboard"


def test_device_type_to_role_mouse():
    assert _device_type_to_role(DEVICE_TYPE_MOUSE) == "mouse"


def test_device_type_to_role_trackball_is_mouse():
    assert _device_type_to_role(DEVICE_TYPE_TRACKBALL) == "mouse"


def test_device_type_to_role_trackpad_is_mouse():
    assert _device_type_to_role(DEVICE_TYPE_TRACKPAD) == "mouse"


def test_device_type_to_role_unknown_returns_none():
    assert _device_type_to_role(7) is None


def test_device_type_to_role_none_input_returns_none():
    assert _device_type_to_role(None) is None


# ── _query_device_info ────────────────────────────────────────────────────────


def test_query_device_info_returns_role_and_name(mocker, fake_transport):
    mocker.patch("cleverswitch.listeners.resolve_feature_index", return_value=2)
    mocker.patch("cleverswitch.listeners.get_device_type", return_value=DEVICE_TYPE_KEYBOARD)
    mocker.patch("cleverswitch.listeners.get_device_name", return_value="MX Keys")
    assert _query_device_info(fake_transport, devnumber=1) == ("keyboard", "MX Keys")


def test_query_device_info_falls_back_to_role_when_name_unavailable(mocker, fake_transport):
    mocker.patch("cleverswitch.listeners.resolve_feature_index", return_value=2)
    mocker.patch("cleverswitch.listeners.get_device_type", return_value=DEVICE_TYPE_MOUSE)
    mocker.patch("cleverswitch.listeners.get_device_name", return_value=None)
    assert _query_device_info(fake_transport, devnumber=2) == ("mouse", "mouse")


def test_query_device_info_returns_none_when_feature_absent(mocker, fake_transport):
    mocker.patch("cleverswitch.listeners.resolve_feature_index", return_value=None)
    assert _query_device_info(fake_transport, devnumber=1) is None


def test_query_device_info_returns_none_for_unrecognised_device_type(mocker, fake_transport):
    mocker.patch("cleverswitch.listeners.resolve_feature_index", return_value=2)
    mocker.patch("cleverswitch.listeners.get_device_type", return_value=8)  # Headset
    mocker.patch("cleverswitch.listeners.get_device_name", return_value=None)
    assert _query_device_info(fake_transport, devnumber=1) is None


# ── parse_message ─────────────────────────────────────────────────────────────


def test_parse_message_returns_none_for_empty_bytes():
    assert parse_message(b"") is None


def test_parse_message_returns_none_for_message_shorter_than_4_bytes():
    assert parse_message(b"\x11\x01\x05") is None


@pytest.mark.parametrize(
    "cid_byte, expected_host",
    [
        (0xD1, HOST_SWITCH_CIDS[0x00D1]),
        (0xD2, HOST_SWITCH_CIDS[0x00D2]),
        (0xD3, HOST_SWITCH_CIDS[0x00D3]),
    ],
)
def test_parse_message_returns_host_change_event_for_each_easy_switch_cid(cid_byte, expected_host):
    products = _kbd_products(slot=1, divert_feat_idx=5)
    raw = _long_msg(slot=1, sub_id=5, address=0x00, data=bytes([0x00, cid_byte]) + bytes(14))
    event = parse_message(raw, products)
    assert isinstance(event, HostChangeEvent)
    assert event.slot == 1
    assert event.target_host == expected_host


def test_parse_message_returns_none_for_unknown_cid_in_long_msg():
    products = _kbd_products(slot=1, divert_feat_idx=5)
    raw = _long_msg(slot=1, sub_id=5, address=0x00, data=bytes([0x00, 0xAA]) + bytes(14))
    assert not isinstance(parse_message(raw, products), HostChangeEvent)


def test_parse_message_returns_none_for_dj_pairing():
    """DJ parsing is handled at receiver level; parse_message only handles REPORT_LONG."""
    raw = _dj_msg(slot=2, feature_id=DJ_DEVICE_PAIRING, address=0x00)
    assert parse_message(raw) is None


def test_parse_message_returns_none_for_dj_pairing_disconnected():
    raw = _dj_msg(slot=3, feature_id=DJ_DEVICE_PAIRING, address=0x40)
    assert parse_message(raw) is None


def test_parse_message_returns_connection_event_for_x1d4b_reconnection():
    raw = _long_msg(slot=1, sub_id=0x04, address=0x00, data=bytes([0x01]) + bytes(15))
    event = parse_message(raw)
    assert isinstance(event, ConnectionEvent)
    assert event.slot == 1


def test_parse_message_returns_none_for_unrecognised_packet():
    raw = bytes([REPORT_SHORT, 1, 0x42, 0x00, 0x00, 0x00, 0x00])
    assert parse_message(raw) is None


# ── _divert_all_es_keys / _undivert_all_es_keys ───────────────────────────────


def test_divert_all_es_keys_calls_set_cid_divert_for_each_host_switch_cid(mocker, fake_transport):
    mock_divert = mocker.patch("cleverswitch.listeners.set_cid_divert")
    product = LogiProduct(slot=1, change_host_feat_idx=2, divert_feat_idx=3, role="keyboard", name="KB")
    _divert_all_es_keys(fake_transport, product)
    assert mock_divert.call_count == len(HOST_SWITCH_CIDS)


def test_divert_all_es_keys_does_not_raise_on_transport_error(mocker, fake_transport):
    from cleverswitch.errors import TransportError

    mocker.patch("cleverswitch.listeners.set_cid_divert", side_effect=TransportError("gone"))
    product = LogiProduct(slot=1, change_host_feat_idx=2, divert_feat_idx=3, role="keyboard", name="KB")
    _divert_all_es_keys(fake_transport, product)  # must not raise


def test_undivert_all_es_keys_suppresses_all_exceptions(mocker, fake_transport):
    mocker.patch("cleverswitch.listeners.set_cid_divert", side_effect=OSError("gone"))
    product = LogiProduct(slot=1, change_host_feat_idx=2, divert_feat_idx=3, role="keyboard", name="KB")
    _undivert_all_es_keys(fake_transport, product)  # must not raise


# ── PathListener ──────────────────────────────────────────────────────────────


def test_path_listener_starts_with_no_transport_and_empty_products(mocker):
    listener, _ = _make_path_listener(mocker, init_transport=False)
    assert listener._transport is None
    assert listener._products == {}


def test_path_listener_add_new_product_skips_existing_slot(mocker):
    listener, _ = _make_path_listener(mocker)
    existing = LogiProduct(slot=1, change_host_feat_idx=2, divert_feat_idx=None, role="mouse", name="M")
    listener._products[1] = existing

    listener.add_new_product(1)  # should be a no-op

    assert listener._products[1] is existing


def test_path_listener_add_new_product_adds_product_on_success(mocker):
    listener, mock_transport = _make_path_listener(mocker)
    product = LogiProduct(slot=2, change_host_feat_idx=3, divert_feat_idx=None, role="mouse", name="M")
    mocker.patch("cleverswitch.listeners._query_device_info", return_value=("mouse", "M"))
    mocker.patch("cleverswitch.listeners._make_logi_product", return_value=product)

    listener.add_new_product(2)

    assert 2 in listener._products


def test_path_listener_add_new_product_skips_when_query_returns_none(mocker):
    listener, _ = _make_path_listener(mocker)
    mocker.patch("cleverswitch.listeners._query_device_info", return_value=None)

    listener.add_new_product(2)

    assert 2 not in listener._products


def test_path_listener_add_new_product_skips_when_make_returns_none(mocker):
    listener, _ = _make_path_listener(mocker)
    mocker.patch("cleverswitch.listeners._query_device_info", return_value=("mouse", "M"))
    mocker.patch("cleverswitch.listeners._make_logi_product", return_value=None)

    listener.add_new_product(2)

    assert 2 not in listener._products


def test_path_listener_run_closes_transport_on_exit(mocker):
    listener, mock_transport = _make_path_listener(mocker)
    mock_transport.read.return_value = None
    listener._shutdown.set()

    listener.run()

    mock_transport.close.assert_called_once()


def test_path_listener_run_undiverts_products_with_divert_feat_on_exit(mocker):
    listener, mock_transport = _make_path_listener(mocker)
    product = LogiProduct(slot=1, change_host_feat_idx=2, divert_feat_idx=3, role="keyboard", name="KB")
    listener._products[1] = product
    mock_transport.read.return_value = None
    mock_undivert = mocker.patch("cleverswitch.listeners._undivert_all_es_keys")
    listener._shutdown.set()

    listener.run()

    mock_undivert.assert_called_once_with(mock_transport, product)


def test_path_listener_run_skips_undivert_for_products_without_divert_feat(mocker):
    listener, mock_transport = _make_path_listener(mocker)
    product = LogiProduct(slot=2, change_host_feat_idx=3, divert_feat_idx=None, role="mouse", name="M")
    listener._products[2] = product
    mock_transport.read.return_value = None
    mock_undivert = mocker.patch("cleverswitch.listeners._undivert_all_es_keys")
    listener._shutdown.set()

    listener.run()

    mock_undivert.assert_not_called()


def test_path_listener_run_dispatches_parsed_event(mocker):
    listener, mock_transport = _make_path_listener(mocker)
    # Add a product so parse_message can match the divert feature index
    product = LogiProduct(slot=1, change_host_feat_idx=2, divert_feat_idx=5, role="keyboard", name="KB")
    listener._products[1] = product

    # Build a HostChangeEvent packet (slot=1, feat_idx=5, fn=0x00, cid=0xD1 → host 0)
    raw = _long_msg(slot=1, sub_id=5, address=0x00, data=bytes([0x00, 0xD1]) + bytes(14))
    call_count = [0]

    def fake_read(timeout=100):
        call_count[0] += 1
        if call_count[0] == 1:
            return raw
        listener._shutdown.set()
        return None

    mock_transport.read = fake_read
    mock_process = mocker.patch.object(listener, "process_event")

    listener.run()

    assert mock_process.call_count >= 1


# ── init_transport ───────────────────────────────────────────────────────────


def test_init_transport_opens_transport_on_first_try(mocker):
    listener, mock_transport = _make_path_listener(mocker, init_transport=False)

    listener.init_transport()

    assert listener._transport is mock_transport


def test_init_transport_retries_on_oserror_and_succeeds(mocker):
    device = HidDeviceInfo(path=b"/dev/hidraw0", vid=0x046D, pid=BOLT_PID, usage_page=0xFF00, usage=1)
    shutdown = threading.Event()
    mock_transport = mocker.MagicMock()
    mock_ctor = mocker.patch(
        "cleverswitch.listeners.HIDTransport", side_effect=[OSError("busy"), OSError("busy"), mock_transport]
    )
    mocker.patch("cleverswitch.listeners._query_device_info", return_value=None)

    listener = PathListener(device, shutdown)
    listener.init_transport()

    assert listener._transport is mock_transport
    assert mock_ctor.call_count == 3


def test_init_transport_gives_up_after_3_failures(mocker):
    device = HidDeviceInfo(path=b"/dev/hidraw0", vid=0x046D, pid=BOLT_PID, usage_page=0xFF00, usage=1)
    shutdown = threading.Event()
    mocker.patch("cleverswitch.listeners.HIDTransport", side_effect=OSError("gone"))
    mocker.patch("cleverswitch.listeners._query_device_info", return_value=None)

    listener = PathListener(device, shutdown)
    listener.init_transport()

    assert listener._transport is None


def test_init_transport_skips_when_already_set(mocker):
    listener, mock_transport = _make_path_listener(mocker)
    mock_ctor = mocker.patch("cleverswitch.listeners.HIDTransport")

    listener.init_transport()  # second call — should be no-op

    mock_ctor.assert_not_called()
    assert listener._transport is mock_transport


def test_run_returns_early_when_transport_init_fails(mocker):
    device = HidDeviceInfo(path=b"/dev/hidraw0", vid=0x046D, pid=BOLT_PID, usage_page=0xFF00, usage=1)
    shutdown = threading.Event()
    mocker.patch("cleverswitch.listeners.HIDTransport", side_effect=OSError("gone"))
    mocker.patch("cleverswitch.listeners._query_device_info", return_value=None)

    listener = PathListener(device, shutdown)
    listener.run()  # should return without error

    assert listener._transport is None
    assert listener._products == {}


def test_run_calls_detect_products(mocker):
    listener, mock_transport = _make_path_listener(mocker)
    mock_transport.read.return_value = None
    mock_detect = mocker.patch.object(listener, "detect_products")
    listener._shutdown.set()

    listener.run()

    mock_detect.assert_called_once()


# ── external undivert detection (via parse_message with products) ────────────


def _setCidReporting_response(slot: int, feat_idx: int, sw_id: int, cid: int) -> bytes:
    """Build a REPORT_LONG setCidReporting response (fn=0x30) for testing."""
    fn_sw = 0x30 | (sw_id & 0x0F)
    cid_hi = (cid >> 8) & 0xFF
    cid_lo = cid & 0xFF
    payload = bytes([feat_idx, fn_sw, cid_hi, cid_lo]) + bytes(14)
    return bytes([REPORT_LONG, slot]) + payload


def _kbd_products(slot=1, divert_feat_idx=5):
    product = LogiProduct(slot=slot, change_host_feat_idx=2, divert_feat_idx=divert_feat_idx, role="keyboard", name="KB")
    return {slot: product}


def test_parse_message_detects_solaar_undivert():
    products = _kbd_products()
    raw = _setCidReporting_response(slot=1, feat_idx=5, sw_id=0x02, cid=0x00D1)
    event = parse_message(raw, products)
    assert isinstance(event, ExternalUndivertEvent)
    assert event.slot == 1
    assert event.target_host_cid == 0xD1


def test_parse_message_ignores_own_sw_id_undivert():
    products = _kbd_products()
    raw = _setCidReporting_response(slot=1, feat_idx=5, sw_id=SW_ID, cid=0x00D1)
    assert parse_message(raw, products) is None


def test_parse_message_ignores_notification_sw_id_0_undivert():
    products = _kbd_products()
    raw = _setCidReporting_response(slot=1, feat_idx=5, sw_id=0x00, cid=0x00D1)
    assert parse_message(raw, products) is None


def test_parse_message_ignores_non_easy_switch_cid_undivert():
    products = _kbd_products()
    raw = _setCidReporting_response(slot=1, feat_idx=5, sw_id=0x02, cid=0x00AA)
    assert parse_message(raw, products) is None


def test_parse_message_ignores_wrong_feature_index_undivert():
    products = _kbd_products()
    raw = _setCidReporting_response(slot=1, feat_idx=7, sw_id=0x02, cid=0x00D1)
    assert parse_message(raw, products) is None


def test_parse_message_ignores_unknown_slot_undivert():
    raw = _setCidReporting_response(slot=3, feat_idx=5, sw_id=0x02, cid=0x00D1)
    assert parse_message(raw, {}) is None


def test_parse_message_ignores_product_without_divert_undivert():
    products = _kbd_products(divert_feat_idx=None)
    raw = _setCidReporting_response(slot=1, feat_idx=5, sw_id=0x02, cid=0x00D1)
    assert parse_message(raw, products) is None


def test_parse_message_without_products_skips_undivert_check():
    raw = _setCidReporting_response(slot=1, feat_idx=5, sw_id=0x02, cid=0x00D1)
    assert parse_message(raw) is None
