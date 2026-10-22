"""Unit tests for gateway/hid_gateway_ble.py."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from cleverswitch.event.link_channel_changed_event import LinkChannelChangedEvent
from cleverswitch.event.transport_connected_event import TransportConnectedEvent
from cleverswitch.event.transport_disconnected_event import TransportDisconnectedEvent
from cleverswitch.gateway.hid_gateway_ble import HidGatewayBLE
from cleverswitch.gateway.hid_gateway_bt import HidGatewayBT
from cleverswitch.hidpp.transport import HidDeviceInfo
from cleverswitch.listener.event_listener import EventListener


def _device_info(pid=0xB023):
    return HidDeviceInfo(
        path=b"/dev/hidraw1",
        vid=0x046D,
        pid=pid,
        usage_page=0xFF43,
        usage=0x0202,
        connection_type="bluetooth",
    )


def _make_gw(pid=0xB023):
    event_listener = MagicMock(spec=EventListener)
    gw = HidGatewayBLE(_device_info(pid=pid), event_listener)
    return gw, event_listener


def _connected_event(pid=0xB023):
    return TransportConnectedEvent(slot=0, pid=pid, connection_type="bluetooth")


# ── Construction ─────────────────────────────────────────────────────────────


def test_inherits_from_hid_gateway_bt():
    gw, _ = _make_gw()
    assert isinstance(gw, HidGatewayBT)


def test_initial_state():
    gw, _ = _make_gw()
    assert not gw._connected
    assert not gw._ever_connected
    assert not gw._stop.is_set()


# ── close() ──────────────────────────────────────────────────────────────────


def test_close_sets_stop_event():
    gw, _ = _make_gw()
    gw._transport = MagicMock()
    gw.close()
    assert gw._stop.is_set()


def test_close_also_closes_transport():
    gw, _ = _make_gw()
    mock_transport = MagicMock()
    gw._transport = mock_transport
    gw.close()
    mock_transport.close.assert_called_once()


# ── run() — _BLE_OK=False branch ─────────────────────────────────────────────


def test_run_skips_ble_thread_when_ble_unavailable(mocker):
    """When bleak is not importable, run() logs a warning and falls through to HID-only loop."""
    mocker.patch("cleverswitch.gateway.hid_gateway_ble._BLE_OK", False)

    gw, _ = _make_gw()
    gw._stop.set()  # exit immediately after first iteration check

    with patch.object(gw, "_try_connect"), patch.object(gw._gatt, "start") as start:
        gw.run()

    start.assert_not_called()


def test_run_logs_warning_when_ble_unavailable(mocker, caplog):
    import logging

    mocker.patch("cleverswitch.gateway.hid_gateway_ble._BLE_OK", False)

    gw, _ = _make_gw(pid=0xB023)
    gw._stop.set()

    with patch.object(gw, "_try_connect"), caplog.at_level(logging.WARNING):
        gw.run()

    assert any("BLE notify path disabled" in r.message for r in caplog.records)


def test_run_starts_gatt_channel_when_ble_ok(mocker):
    mocker.patch("cleverswitch.gateway.hid_gateway_ble._BLE_OK", True)

    gw, _ = _make_gw()
    gw._stop.set()

    with patch.object(gw, "_try_connect"), patch.object(gw._gatt, "start") as start:
        gw.run()

    start.assert_called_once()


def test_run_calls_try_connect_when_not_connected(mocker):
    mocker.patch("cleverswitch.gateway.hid_gateway_ble._BLE_OK", False)

    gw, _ = _make_gw()
    call_count = [0]

    def fake_try_connect():
        call_count[0] += 1
        gw._stop.set()

    with patch.object(gw, "_try_connect", side_effect=fake_try_connect):
        gw.run()

    assert call_count[0] == 1


# ── GATT channel wiring ──────────────────────────────────────────────────────


def test_gatt_channel_is_bound_to_this_gateway():
    gw, event_listener = _make_gw(pid=0xB023)
    assert gw._gatt._pid == 0xB023
    assert gw._gatt._on_report == event_listener.listen
    assert gw._gatt._stop is gw._stop


def test_do_write_uses_gatt_when_it_accepts_the_write(mocker):
    gw, _ = _make_gw()
    mocker.patch.object(gw._gatt, "write", return_value=True)
    transport = MagicMock()

    gw._do_write(transport, b"\x11\xff\x08\x3e")

    gw._gatt.write.assert_called_once_with(b"\x11\xff\x08\x3e")
    transport.write_output_report.assert_not_called()


def test_do_write_falls_back_to_hid_when_gatt_declines(mocker):
    gw, _ = _make_gw()
    mocker.patch.object(gw._gatt, "write", return_value=False)
    transport = MagicMock()

    gw._do_write(transport, b"\x11\xff\x08\x3e")

    transport.write_output_report.assert_called_once_with(b"\x11\xff\x08\x3e")


# ── HID owns presence; GATT follows it ───────────────────────────────────────


def test_connect_emits_immediately_and_activates_gatt():
    """No waiting for GATT: the reader thread must never block on the other channel."""
    gw, event_listener = _make_gw()

    gw._set_connected(True)

    event_listener.emit.assert_called_once_with(_connected_event())
    assert gw._gatt._active.is_set()


def test_disconnect_emits_and_deactivates_gatt():
    gw, event_listener = _make_gw(pid=0xB023)
    gw._set_connected(True)
    event_listener.emit.reset_mock()

    gw._set_connected(False)

    event_listener.emit.assert_called_once_with(TransportDisconnectedEvent(slot=0, pid=0xB023))
    assert not gw._gatt._active.is_set()


@pytest.mark.parametrize("up", [True, False])
def test_gatt_state_is_published_as_channel_change(up):
    gw, event_listener = _make_gw(pid=0xB023)

    gw._gatt._on_state(up)

    event_listener.emit.assert_called_once_with(LinkChannelChangedEvent(slot=0, pid=0xB023, channel="gatt", up=up))


def test_gatt_drop_leaves_the_device_connected():
    gw, event_listener = _make_gw()
    gw._set_connected(True)
    event_listener.emit.reset_mock()

    gw._gatt._on_state(False)

    assert gw._connected
    assert not any(isinstance(c.args[0], TransportDisconnectedEvent) for c in event_listener.emit.call_args_list)


# ── Handle ownership (issue #108) ────────────────────────────────────────────


def test_run_closes_its_own_transport_on_exit(mocker):
    """run() fully overrides the base loop, so it needs the same teardown."""
    mocker.patch("cleverswitch.gateway.hid_gateway_ble._BLE_OK", False)
    gw, _ = _make_gw()
    transport = MagicMock()
    gw._transport = transport
    gw._stop.set()

    gw.run()

    transport.close.assert_called_once()


def test_close_from_foreign_thread_lets_ble_reader_close_its_handle(mocker, make_fake_transport):
    mocker.patch("cleverswitch.gateway.hid_gateway_ble._BLE_OK", False)
    gw, _ = _make_gw()
    transport = make_fake_transport()
    gw._transport = transport
    gw._connected = True  # skip _try_connect; the loop just sleeps
    gw.start()
    time.sleep(0.05)

    gw.close()

    assert not gw.is_alive()
    assert transport.close_count == 1
    assert transport.closed_by == gw.name


# ── _do_write: ATT write mode (issue #109) ───────────────────────────────────
