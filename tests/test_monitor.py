"""Unit tests for event processor logic.

Covers:
  - ConnectionProcessor — handles ConnectionEvent, diverts ES keys
  - HostChangeProcessor — handles HostChangeEvent, calls _switch for each product
  - _divert_all_es_keys — calls set_cid_divert for each HOST_SWITCH_CID
  - _switch — calls send_change_host with correct arguments
"""

from __future__ import annotations

import threading

import pytest

from cleverswitch.event_processors import (
    ConnectionProcessor,
    HostChangeProcessor,
    Processor,
    _divert_all_es_keys,
    _switch,
)
from cleverswitch.hidpp.constants import HOST_SWITCH_CIDS
from cleverswitch.model import (
    EventProcessorArguments,
    ConnectionEvent,
    HostChangeEvent,
    LogiProduct,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_product(role: str, slot: int, divert_feat_idx: int | None = None) -> LogiProduct:
    return LogiProduct(
        slot=slot,
        change_host_feat_idx=1,
        divert_feat_idx=divert_feat_idx,
        role=role,
        name=role,
    )


def _make_args(transport, products: dict, event) -> EventProcessorArguments:
    return EventProcessorArguments(products=products, transport=transport, event=event, shutdown=threading.Event())


# ── ConnectionProcessor ─────────────────────────────────────────────────────


def test_connection_processor_diverts_keys_when_divert_feat_set(mocker, fake_transport):
    mock_divert = mocker.patch("cleverswitch.event_processors._divert_all_es_keys")
    product = _make_product("keyboard", slot=1, divert_feat_idx=3)
    products = {1: product}
    args = _make_args(fake_transport, products, ConnectionEvent(slot=1))

    ConnectionProcessor().process(args)

    mock_divert.assert_called_once_with(fake_transport, product)


def test_connection_processor_does_not_divert_when_no_divert_feat(mocker, fake_transport):
    mock_divert = mocker.patch("cleverswitch.event_processors._divert_all_es_keys")
    product = _make_product("mouse", slot=2, divert_feat_idx=None)
    products = {2: product}
    args = _make_args(fake_transport, products, ConnectionEvent(slot=2))

    ConnectionProcessor().process(args)

    mock_divert.assert_not_called()


def test_connection_processor_ignores_non_connection_events(mocker, fake_transport):
    mock_divert = mocker.patch("cleverswitch.event_processors._divert_all_es_keys")
    product = _make_product("keyboard", slot=1, divert_feat_idx=3)
    products = {1: product}
    args = _make_args(fake_transport, products, HostChangeEvent(slot=1, target_host=2))

    ConnectionProcessor().process(args)

    mock_divert.assert_not_called()


# ── HostChangeProcessor ───────────────────────────────────────────────────────


def test_host_change_processor_calls_switch_for_each_product(mocker, fake_transport):
    mock_switch = mocker.patch("cleverswitch.event_processors._switch")
    kbd = _make_product("keyboard", slot=1)
    mouse = _make_product("mouse", slot=2)
    products = {1: kbd, 2: mouse}
    args = _make_args(fake_transport, products, HostChangeEvent(slot=1, target_host=2))

    HostChangeProcessor().process(args)

    assert mock_switch.call_count == 2


def test_host_change_processor_passes_correct_target_host(mocker, fake_transport):
    calls = []
    mocker.patch("cleverswitch.event_processors._switch", side_effect=lambda t, p, h: calls.append(h))
    kbd = _make_product("keyboard", slot=1)
    products = {1: kbd}
    args = _make_args(fake_transport, products, HostChangeEvent(slot=1, target_host=1))

    HostChangeProcessor().process(args)

    assert calls == [1]


def test_host_change_processor_ignores_non_host_change_events(mocker, fake_transport):
    mock_switch = mocker.patch("cleverswitch.event_processors._switch")
    products = {1: _make_product("keyboard", slot=1)}
    args = _make_args(fake_transport, products, ConnectionEvent(slot=1))

    HostChangeProcessor().process(args)

    mock_switch.assert_not_called()


# ── _divert_all_es_keys() ─────────────────────────────────────────────────────


def test_divert_all_es_keys_calls_set_cid_divert_for_each_host_switch_cid(mocker, fake_transport):
    mock_divert = mocker.patch("cleverswitch.event_processors.set_cid_divert")
    product = _make_product("keyboard", slot=1, divert_feat_idx=3)

    _divert_all_es_keys(fake_transport, product)

    assert mock_divert.call_count == len(HOST_SWITCH_CIDS)


def test_divert_all_es_keys_passes_diverted_true(mocker, fake_transport):
    calls = []
    mocker.patch(
        "cleverswitch.event_processors.set_cid_divert",
        side_effect=lambda *a, **kw: calls.append(a),
    )
    product = _make_product("keyboard", slot=1, divert_feat_idx=3)

    _divert_all_es_keys(fake_transport, product)

    assert all(args[4] is True for args in calls)


# ── Processor base ───────────────────────────────────────────────────────────


def test_processor_base_process_method_returns_none(fake_transport):
    product = _make_product("keyboard", slot=1)
    args = _make_args(fake_transport, {1: product}, ConnectionEvent(slot=1))
    result = Processor().process(args)
    assert result is None


# ── _switch() ─────────────────────────────────────────────────────────────────


def test_switch_calls_send_change_host_with_correct_args(mocker, fake_transport):
    mock_send = mocker.patch("cleverswitch.event_processors.send_change_host")
    product = _make_product("keyboard", slot=1)

    _switch(fake_transport, product, target_host=2)

    mock_send.assert_called_once_with(
        fake_transport,
        product.slot,
        product.change_host_feat_idx,
        2,
    )
