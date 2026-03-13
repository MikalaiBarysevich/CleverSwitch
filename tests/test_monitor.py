"""Unit tests for listener event handling logic.

Covers:
  - ReceiverListener._handle_connection — diverts ES keys on reconnect
  - ReceiverListener._handle_external_undivert — re-diverts single CID
  - BaseListener._handle_host_change — sends CHANGE_HOST via registry
  - _divert_all_es_keys — calls set_cid_divert for each HOST_SWITCH_CID
"""

from __future__ import annotations

import threading

import pytest

from cleverswitch.hidpp.constants import BOLT_PID, HOST_SWITCH_CIDS
from cleverswitch.hidpp.transport import HidDeviceInfo
from cleverswitch.listeners import (
    ProductRegistry,
    ReceiverListener,
    _divert_all_es_keys,
)
from cleverswitch.model import (
    ConnectionEvent,
    ExternalUndivertEvent,
    HostChangeEvent,
    LogiProduct,
    ProductEntry,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_product(role: str, slot: int, divert_feat_idx: int | None = None) -> LogiProduct:
    return LogiProduct(
        slot=slot,
        change_host_feat_idx=1,
        divert_feat_idx=divert_feat_idx,
        role=role,
        name=role,
    )


def _receiver_device():
    return HidDeviceInfo(path=b"/dev/hidraw0", vid=0x046D, pid=BOLT_PID, usage_page=0xFF00, usage=0x0002, connection_type="receiver")


def _make_listener(mocker, registry=None):
    device = _receiver_device()
    shutdown = threading.Event()
    if registry is None:
        registry = ProductRegistry()
    mock_transport = mocker.MagicMock()
    mocker.patch("cleverswitch.listeners.HIDTransport", return_value=mock_transport)
    mocker.patch("cleverswitch.listeners._query_device_info", return_value=None)
    listener = ReceiverListener(device, shutdown, registry)
    listener._init_transport()
    return listener, mock_transport


# ── Connection handling ──────────────────────────────────────────────────────


def test_handle_connection_diverts_keys_when_divert_feat_set(mocker):
    listener, mock_transport = _make_listener(mocker)
    mock_divert = mocker.patch("cleverswitch.listeners._divert_all_es_keys")
    product = _make_product("keyboard", slot=1, divert_feat_idx=3)
    listener._products[1] = product

    listener._handle_connection(ConnectionEvent(slot=1))

    mock_divert.assert_called_once_with(mock_transport, product)


def test_handle_connection_does_not_divert_when_no_divert_feat(mocker):
    listener, _ = _make_listener(mocker)
    mock_divert = mocker.patch("cleverswitch.listeners._divert_all_es_keys")
    product = _make_product("mouse", slot=2, divert_feat_idx=None)
    listener._products[2] = product

    listener._handle_connection(ConnectionEvent(slot=2))

    mock_divert.assert_not_called()


def test_handle_connection_ignores_unknown_slot(mocker):
    listener, _ = _make_listener(mocker)
    mock_divert = mocker.patch("cleverswitch.listeners._divert_all_es_keys")

    listener._handle_connection(ConnectionEvent(slot=5))

    mock_divert.assert_not_called()


# ── Host change handling ─────────────────────────────────────────────────────


def test_host_change_sends_to_all_registry_entries(mocker, fake_transport):
    registry = ProductRegistry()
    entry1 = ProductEntry(fake_transport, 1, 2, None, "keyboard", "KB")
    entry2 = ProductEntry(fake_transport, 2, 3, None, "mouse", "M")
    registry.register((b"/dev/hidraw0", 1), entry1)
    registry.register((b"/dev/hidraw0", 2), entry2)

    listener, _ = _make_listener(mocker, registry=registry)
    mock_send = mocker.patch("cleverswitch.listeners.send_change_host")

    listener._handle_host_change(HostChangeEvent(slot=1, target_host=2))

    assert mock_send.call_count == 2


def test_host_change_passes_correct_target_host(mocker, fake_transport):
    registry = ProductRegistry()
    entry = ProductEntry(fake_transport, 1, 5, None, "keyboard", "KB")
    registry.register((b"/dev/hidraw0", 1), entry)

    listener, _ = _make_listener(mocker, registry=registry)
    mock_send = mocker.patch("cleverswitch.listeners.send_change_host")

    listener._handle_host_change(HostChangeEvent(slot=1, target_host=1))

    mock_send.assert_called_once_with(fake_transport, 1, 5, 1)


def test_host_change_ignores_send_failure(mocker, fake_transport):
    registry = ProductRegistry()
    entry = ProductEntry(fake_transport, 1, 2, None, "keyboard", "KB")
    registry.register((b"/dev/hidraw0", 1), entry)

    listener, _ = _make_listener(mocker, registry=registry)
    mocker.patch("cleverswitch.listeners.send_change_host", side_effect=Exception("transport gone"))

    listener._handle_host_change(HostChangeEvent(slot=1, target_host=0))  # must not raise


# ── External undivert handling ───────────────────────────────────────────────


def test_handle_external_undivert_rediverts_single_cid(mocker):
    listener, mock_transport = _make_listener(mocker)
    mock_divert = mocker.patch("cleverswitch.listeners._divert_single_es_key")
    product = _make_product("keyboard", slot=1, divert_feat_idx=3)
    listener._products[1] = product

    listener._handle_external_undivert(ExternalUndivertEvent(slot=1, target_host_cid=0x00D1))

    mock_divert.assert_called_once_with(mock_transport, product, 0x00D1)


def test_handle_external_undivert_ignores_product_without_divert(mocker):
    listener, _ = _make_listener(mocker)
    mock_divert = mocker.patch("cleverswitch.listeners._divert_single_es_key")
    product = _make_product("mouse", slot=2, divert_feat_idx=None)
    listener._products[2] = product

    listener._handle_external_undivert(ExternalUndivertEvent(slot=2, target_host_cid=0x00D1))

    mock_divert.assert_not_called()


# ── _divert_all_es_keys ─────────────────────────────────────────────────────


def test_divert_all_es_keys_calls_set_cid_divert_for_each_host_switch_cid(mocker, fake_transport):
    mock_divert = mocker.patch("cleverswitch.listeners.set_cid_divert")
    product = _make_product("keyboard", slot=1, divert_feat_idx=3)

    _divert_all_es_keys(fake_transport, product)

    assert mock_divert.call_count == len(HOST_SWITCH_CIDS)


def test_divert_all_es_keys_passes_diverted_true(mocker, fake_transport):
    calls = []
    mocker.patch(
        "cleverswitch.listeners.set_cid_divert",
        side_effect=lambda *a, **kw: calls.append(a),
    )
    product = _make_product("keyboard", slot=1, divert_feat_idx=3)

    _divert_all_es_keys(fake_transport, product)

    assert all(args[4] is True for args in calls)
