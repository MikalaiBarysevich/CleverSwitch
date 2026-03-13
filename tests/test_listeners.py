"""Unit tests for listeners.py.

Covers:
  - parse_message        — raw HID++ bytes → structured event or None
  - _device_type_to_role — x0005 deviceType → 'keyboard' / 'mouse' / None
  - _query_device_info   — feature resolution → (role, name) or None
  - _divert_all_es_keys  — calls set_cid_divert for each HOST_SWITCH_CID
  - _undivert_all_es_keys — same, but suppresses all exceptions
  - ReceiverListener     — per-receiver thread lifecycle
  - BTListener           — per-BT-device thread lifecycle
  - ProductRegistry      — thread-safe product tracking
"""

from __future__ import annotations

import struct
import threading

import pytest

from cleverswitch.hidpp.constants import (
    BOLT_PID,
    DEVICE_RECEIVER,
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
    BTListener,
    ProductRegistry,
    ReceiverListener,
    _device_type_to_role,
    _divert_all_es_keys,
    _query_device_info,
    _undivert_all_es_keys,
    parse_message,
)
from cleverswitch.model import ConnectionEvent, ExternalUndivertEvent, HostChangeEvent, LogiProduct, ProductEntry


# ── Helpers ───────────────────────────────────────────────────────────────────


def _long_msg(slot: int, sub_id: int, address: int, data: bytes) -> bytes:
    payload = bytes([sub_id, address]) + data
    return struct.pack("!BB18s", REPORT_LONG, slot, payload)


def _dj_msg(slot: int, feature_id: int, address: int) -> bytes:
    payload = bytes([feature_id, address]) + bytes(MSG_DJ_LEN - 3)
    return bytes([REPORT_DJ, slot]) + payload


def _receiver_device():
    return HidDeviceInfo(path=b"/dev/hidraw0", vid=0x046D, pid=BOLT_PID, usage_page=0xFF00, usage=0x0002, connection_type="receiver")


def _bt_device(pid=0xB023):
    return HidDeviceInfo(path=b"/dev/hidraw1", vid=0x046D, pid=pid, usage_page=0xFF43, usage=0x0202, connection_type="bluetooth")


def _make_receiver_listener(mocker, device=None, shutdown=None, registry=None, init_transport=True):
    """Instantiate ReceiverListener with HIDTransport and _query_device_info mocked out."""
    if device is None:
        device = _receiver_device()
    if shutdown is None:
        shutdown = threading.Event()
    if registry is None:
        registry = ProductRegistry()

    mock_transport = mocker.MagicMock()
    mocker.patch("cleverswitch.listeners.HIDTransport", return_value=mock_transport)
    mocker.patch("cleverswitch.listeners._query_device_info", return_value=None)

    listener = ReceiverListener(device, shutdown, registry)
    if init_transport:
        listener._init_transport()
    return listener, mock_transport


def _make_bt_listener(mocker, device=None, shutdown=None, registry=None, init_transport=True):
    """Instantiate BTListener with HIDTransport and _query_device_info mocked out."""
    if device is None:
        device = _bt_device()
    if shutdown is None:
        shutdown = threading.Event()
    if registry is None:
        registry = ProductRegistry()

    mock_transport = mocker.MagicMock()
    mocker.patch("cleverswitch.listeners.HIDTransport", return_value=mock_transport)
    mocker.patch("cleverswitch.listeners._query_device_info", return_value=None)

    listener = BTListener(device, shutdown, registry)
    if init_transport:
        listener._init_transport()
    return listener, mock_transport


# ── ProductRegistry ──────────────────────────────────────────────────────────


def test_registry_register_and_all_entries(fake_transport):
    registry = ProductRegistry()
    entry = ProductEntry(fake_transport, 1, 2, 3, "keyboard", "KB")
    registry.register((b"/dev/hidraw0", 1), entry)
    assert registry.all_entries() == [entry]


def test_registry_unregister(fake_transport):
    registry = ProductRegistry()
    entry = ProductEntry(fake_transport, 1, 2, 3, "keyboard", "KB")
    registry.register((b"/dev/hidraw0", 1), entry)
    registry.unregister((b"/dev/hidraw0", 1))
    assert registry.all_entries() == []


def test_registry_unregister_nonexistent_key():
    registry = ProductRegistry()
    registry.unregister("nonexistent")  # must not raise


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


# ── ReceiverListener ──────────────────────────────────────────────────────────


def test_receiver_listener_starts_with_no_transport_and_empty_products(mocker):
    listener, _ = _make_receiver_listener(mocker, init_transport=False)
    assert listener._transport is None
    assert listener._products == {}


def test_receiver_listener_add_product_skips_existing_slot(mocker):
    listener, _ = _make_receiver_listener(mocker)
    existing = LogiProduct(slot=1, change_host_feat_idx=2, divert_feat_idx=None, role="mouse", name="M")
    listener._products[1] = existing

    listener._add_product(1)  # should be a no-op

    assert listener._products[1] is existing


def test_receiver_listener_add_product_adds_product_on_success(mocker):
    registry = ProductRegistry()
    listener, mock_transport = _make_receiver_listener(mocker, registry=registry)
    product = LogiProduct(slot=2, change_host_feat_idx=3, divert_feat_idx=None, role="mouse", name="M")
    mocker.patch("cleverswitch.listeners._query_device_info", return_value=("mouse", "M"))
    mocker.patch("cleverswitch.listeners._make_logi_product", return_value=product)

    listener._add_product(2)

    assert 2 in listener._products
    assert len(registry.all_entries()) == 1


def test_receiver_listener_add_product_skips_when_query_returns_none(mocker):
    listener, _ = _make_receiver_listener(mocker)
    mocker.patch("cleverswitch.listeners._query_device_info", return_value=None)

    listener._add_product(2)

    assert 2 not in listener._products


def test_receiver_listener_add_product_skips_when_make_returns_none(mocker):
    listener, _ = _make_receiver_listener(mocker)
    mocker.patch("cleverswitch.listeners._query_device_info", return_value=("mouse", "M"))
    mocker.patch("cleverswitch.listeners._make_logi_product", return_value=None)

    listener._add_product(2)

    assert 2 not in listener._products


def test_receiver_listener_run_closes_transport_on_exit(mocker):
    listener, mock_transport = _make_receiver_listener(mocker)
    mock_transport.read.return_value = None
    listener._shutdown.set()

    listener.run()

    mock_transport.close.assert_called_once()


def test_receiver_listener_run_undiverts_products_with_divert_feat_on_exit(mocker):
    listener, mock_transport = _make_receiver_listener(mocker)
    product = LogiProduct(slot=1, change_host_feat_idx=2, divert_feat_idx=3, role="keyboard", name="KB")
    listener._products[1] = product
    mock_transport.read.return_value = None
    mock_undivert = mocker.patch("cleverswitch.listeners._undivert_all_es_keys")
    listener._shutdown.set()

    listener.run()

    mock_undivert.assert_called_once_with(mock_transport, product)


def test_receiver_listener_run_skips_undivert_for_products_without_divert_feat(mocker):
    listener, mock_transport = _make_receiver_listener(mocker)
    product = LogiProduct(slot=2, change_host_feat_idx=3, divert_feat_idx=None, role="mouse", name="M")
    listener._products[2] = product
    mock_transport.read.return_value = None
    mock_undivert = mocker.patch("cleverswitch.listeners._undivert_all_es_keys")
    listener._shutdown.set()

    listener.run()

    mock_undivert.assert_not_called()


def test_receiver_listener_run_dispatches_parsed_event(mocker):
    listener, mock_transport = _make_receiver_listener(mocker)
    product = LogiProduct(slot=1, change_host_feat_idx=2, divert_feat_idx=5, role="keyboard", name="KB")
    listener._products[1] = product

    raw = _long_msg(slot=1, sub_id=5, address=0x00, data=bytes([0x00, 0xD1]) + bytes(14))
    call_count = [0]

    def fake_read(timeout=100):
        call_count[0] += 1
        if call_count[0] == 1:
            return raw
        listener._shutdown.set()
        return None

    mock_transport.read = fake_read
    mock_handle = mocker.patch.object(listener, "_handle_event")

    listener.run()

    assert mock_handle.call_count >= 1


# ── ReceiverListener init_transport ──────────────────────────────────────────


def test_receiver_init_transport_opens_transport_on_first_try(mocker):
    listener, mock_transport = _make_receiver_listener(mocker, init_transport=False)

    listener._init_transport()

    assert listener._transport is mock_transport


def test_receiver_init_transport_retries_on_oserror_and_succeeds(mocker):
    device = _receiver_device()
    shutdown = threading.Event()
    registry = ProductRegistry()
    mock_transport = mocker.MagicMock()
    mock_ctor = mocker.patch(
        "cleverswitch.listeners.HIDTransport", side_effect=[OSError("busy"), OSError("busy"), mock_transport]
    )
    mocker.patch("cleverswitch.listeners._query_device_info", return_value=None)

    listener = ReceiverListener(device, shutdown, registry)
    mocker.patch.object(listener._shutdown, "wait")
    listener._init_transport()

    assert listener._transport is mock_transport
    assert mock_ctor.call_count == 3


def test_receiver_init_transport_gives_up_after_3_failures(mocker):
    device = _receiver_device()
    shutdown = threading.Event()
    registry = ProductRegistry()
    mocker.patch("cleverswitch.listeners.HIDTransport", side_effect=OSError("gone"))
    mocker.patch("cleverswitch.listeners._query_device_info", return_value=None)

    listener = ReceiverListener(device, shutdown, registry)
    mocker.patch.object(listener._shutdown, "wait")
    listener._init_transport()

    assert listener._transport is None


def test_receiver_init_transport_skips_when_already_set(mocker):
    listener, mock_transport = _make_receiver_listener(mocker)
    mock_ctor = mocker.patch("cleverswitch.listeners.HIDTransport")

    listener._init_transport()  # second call — should be no-op

    mock_ctor.assert_not_called()
    assert listener._transport is mock_transport


def test_receiver_run_returns_early_when_transport_init_fails(mocker):
    device = _receiver_device()
    shutdown = threading.Event()
    registry = ProductRegistry()
    mocker.patch("cleverswitch.listeners.HIDTransport", side_effect=OSError("gone"))
    mocker.patch("cleverswitch.listeners._query_device_info", return_value=None)

    listener = ReceiverListener(device, shutdown, registry)
    mocker.patch.object(listener._shutdown, "wait")
    listener.run()

    assert listener._transport is None
    assert listener._products == {}


def test_receiver_run_calls_detect_products(mocker):
    listener, mock_transport = _make_receiver_listener(mocker)
    mock_transport.read.return_value = None
    mock_detect = mocker.patch.object(listener, "_detect_products")
    listener._shutdown.set()

    listener.run()

    mock_detect.assert_called_once()


# ── ReceiverListener host change uses registry ───────────────────────────────


def test_receiver_host_change_sends_to_all_registry_entries(mocker, fake_transport):
    registry = ProductRegistry()
    entry1 = ProductEntry(fake_transport, 1, 2, None, "keyboard", "KB")
    entry2 = ProductEntry(fake_transport, 2, 3, None, "mouse", "M")
    registry.register((b"/dev/hidraw0", 1), entry1)
    registry.register((b"/dev/hidraw0", 2), entry2)

    listener, mock_transport = _make_receiver_listener(mocker, registry=registry)
    mock_send = mocker.patch("cleverswitch.listeners.send_change_host")

    listener._handle_host_change(HostChangeEvent(slot=1, target_host=2))

    assert mock_send.call_count == 2


# ── BTListener ───────────────────────────────────────────────────────────────


def test_bt_listener_detect_products_registers_in_registry(mocker):
    registry = ProductRegistry()
    listener, mock_transport = _make_bt_listener(mocker, registry=registry)
    product = LogiProduct(slot=DEVICE_RECEIVER, change_host_feat_idx=3, divert_feat_idx=None, role="mouse", name="MX Anywhere")
    mocker.patch("cleverswitch.listeners._query_device_info", return_value=("mouse", "MX Anywhere"))
    mocker.patch("cleverswitch.listeners._make_logi_product", return_value=product)

    listener._detect_products()

    assert DEVICE_RECEIVER in listener._products
    entries = registry.all_entries()
    assert len(entries) == 1
    assert entries[0].name == "MX Anywhere"


def test_bt_listener_detect_products_diverts_keys_for_keyboard(mocker):
    registry = ProductRegistry()
    listener, mock_transport = _make_bt_listener(mocker, registry=registry)
    product = LogiProduct(slot=DEVICE_RECEIVER, change_host_feat_idx=3, divert_feat_idx=5, role="keyboard", name="MX Keys")
    mocker.patch("cleverswitch.listeners._query_device_info", return_value=("keyboard", "MX Keys"))
    mocker.patch("cleverswitch.listeners._make_logi_product", return_value=product)
    mock_divert = mocker.patch("cleverswitch.listeners._divert_all_es_keys")

    listener._detect_products()

    mock_divert.assert_called_once_with(mock_transport, product)


def test_bt_listener_cleanup_unregisters_from_registry(mocker):
    registry = ProductRegistry()
    listener, mock_transport = _make_bt_listener(mocker, registry=registry)
    product = LogiProduct(slot=DEVICE_RECEIVER, change_host_feat_idx=3, divert_feat_idx=None, role="mouse", name="M")
    listener._products[DEVICE_RECEIVER] = product
    registry.register(listener._hid_device_info.pid, ProductEntry(mock_transport, DEVICE_RECEIVER, 3, None, "mouse", "M"))

    listener._cleanup()

    assert registry.all_entries() == []
    mock_transport.close.assert_called_once()


def test_bt_listener_init_transport_single_attempt(mocker):
    """BT listener does not retry — single attempt only."""
    device = _bt_device()
    shutdown = threading.Event()
    registry = ProductRegistry()
    mocker.patch("cleverswitch.listeners.HIDTransport", side_effect=OSError("no access"))
    mocker.patch("cleverswitch.listeners._query_device_info", return_value=None)

    listener = BTListener(device, shutdown, registry)
    listener._init_transport()

    assert listener._transport is None


def test_bt_listener_run_returns_early_when_transport_init_fails(mocker):
    device = _bt_device()
    shutdown = threading.Event()
    registry = ProductRegistry()
    mocker.patch("cleverswitch.listeners.HIDTransport", side_effect=OSError("no access"))
    mocker.patch("cleverswitch.listeners._query_device_info", return_value=None)

    listener = BTListener(device, shutdown, registry)
    listener.run()

    assert listener._transport is None


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
