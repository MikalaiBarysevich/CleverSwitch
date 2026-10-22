"""Unit tests for gateway/hid_gateway_ble.py."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

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
    assert gw._gatt._link_up is gw._connected_signal
    assert gw._gatt._stop is gw._stop


def test_gatt_drop_emits_transport_disconnected():
    """A GATT drop runs the inherited HidGatewayBT path that emits the typed disconnect."""
    gw, event_listener = _make_gw(pid=0xB023)
    gw._connected = True

    gw._gatt._on_drop()

    assert not gw._connected
    event_listener.emit.assert_called_once_with(TransportDisconnectedEvent(slot=0, pid=0xB023))


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


# ── _set_connected gating ─────────────────────────────────────────────────────


def test_set_connected_true_blocks_until_ble_subscribed(mocker):
    mocker.patch("cleverswitch.gateway.hid_gateway_ble._BLE_OK", True)
    gw, event_listener = _make_gw()

    fired = threading.Event()

    def call_set_connected():
        gw._set_connected(True)
        fired.set()

    t = threading.Thread(target=call_set_connected, daemon=True)
    t.start()

    # _connected flips immediately so BLE thread can proceed, but event must not fire yet
    assert fired.wait(timeout=0.3) is False
    assert gw._connected is True
    event_listener.emit.assert_not_called()

    # Subscribe — main thread should wake up and emit the connect
    gw._gatt.subscribed.set()
    assert fired.wait(timeout=2.0) is True
    event_listener.emit.assert_called_once_with(_connected_event())


def test_set_connected_true_fires_immediately_when_ble_not_ok(mocker):
    mocker.patch("cleverswitch.gateway.hid_gateway_ble._BLE_OK", False)
    gw, event_listener = _make_gw()

    gw._set_connected(True)

    assert gw._connected is True
    event_listener.emit.assert_called_once_with(_connected_event())


def test_set_connected_true_does_not_fire_if_stop_set_during_wait(mocker):
    mocker.patch("cleverswitch.gateway.hid_gateway_ble._BLE_OK", True)
    gw, event_listener = _make_gw()

    fired = threading.Event()

    def call_set_connected():
        gw._set_connected(True)
        fired.set()

    t = threading.Thread(target=call_set_connected, daemon=True)
    t.start()

    # Don't set subscribed; trigger shutdown instead
    assert fired.wait(timeout=0.3) is False
    gw._stop.set()

    assert fired.wait(timeout=2.0) is True
    event_listener.emit.assert_not_called()


def test_set_connected_false_clears_ble_subscribed_and_fires_disconnect(mocker):
    mocker.patch("cleverswitch.gateway.hid_gateway_ble._BLE_OK", True)
    gw, event_listener = _make_gw()
    gw._connected = True
    gw._gatt.subscribed.set()

    gw._set_connected(False)

    assert gw._connected is False
    assert not gw._gatt.subscribed.is_set()
    event_listener.emit.assert_called_once_with(TransportDisconnectedEvent(slot=0, pid=gw._device_info.pid))


def test_set_connected_true_after_grace_emits_connect(mocker):
    mocker.patch("cleverswitch.gateway.hid_gateway_ble._BLE_OK", True)
    mocker.patch("cleverswitch.gateway.hid_gateway_ble._BLE_SUBSCRIBE_GRACE", 0.0)
    gw, event_listener = _make_gw()

    gw._set_connected(True)

    event_listener.emit.assert_called_once_with(_connected_event())


def test_ble_drop_during_grace_suppresses_connect(mocker):
    """The disconnect already went out; a connect after it would leave the device marked present."""
    mocker.patch("cleverswitch.gateway.hid_gateway_ble._BLE_OK", True)
    mocker.patch("cleverswitch.gateway.hid_gateway_ble._BLE_SUBSCRIBE_GRACE", 0.0)
    gw, event_listener = _make_gw()

    def drop(timeout):
        gw._connected = False
        return False

    mocker.patch.object(gw._gatt.subscribed, "wait", side_effect=drop)

    gw._set_connected(True)

    event_listener.emit.assert_not_called()


# ── _find_peripheral_by_wpid ─────────────────────────────────────────────────


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
