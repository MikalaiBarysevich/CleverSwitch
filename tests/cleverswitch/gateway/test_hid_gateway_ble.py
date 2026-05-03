"""Unit tests for gateway/hid_gateway_ble.py."""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cleverswitch.gateway.hid_gateway_ble import BLE_PREPEND, HidGatewayBLE
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
    thread_cls = mocker.patch("cleverswitch.gateway.hid_gateway_ble.Thread")

    gw, _ = _make_gw()
    gw._stop.set()  # exit immediately after first iteration check

    with patch.object(gw, "_try_connect"):
        gw.run()

    thread_cls.assert_not_called()


def test_run_logs_warning_when_ble_unavailable(mocker, caplog):
    import logging

    mocker.patch("cleverswitch.gateway.hid_gateway_ble._BLE_OK", False)
    mocker.patch("cleverswitch.gateway.hid_gateway_ble.Thread")

    gw, _ = _make_gw(pid=0xB023)
    gw._stop.set()

    with patch.object(gw, "_try_connect"), caplog.at_level(logging.WARNING):
        gw.run()

    assert any("BLE notify path disabled" in r.message for r in caplog.records)


def test_run_spawns_ble_thread_when_ble_ok(mocker):
    mocker.patch("cleverswitch.gateway.hid_gateway_ble._BLE_OK", True)
    mock_thread_instance = MagicMock()
    thread_cls = mocker.patch("cleverswitch.gateway.hid_gateway_ble.Thread", return_value=mock_thread_instance)

    gw, _ = _make_gw()
    gw._stop.set()

    with patch.object(gw, "_try_connect"):
        gw.run()

    thread_cls.assert_called_once()
    mock_thread_instance.start.assert_called_once()


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


# ── _on_notify ────────────────────────────────────────────────────────────────


def test_on_notify_prepends_ble_prepend_and_forwards_to_listener():
    gw, event_listener = _make_gw()
    payload = bytearray([0x11, 0x01, 0x02, 0x03] + [0x00] * 14)
    gw._on_notify(None, payload)

    event_listener.listen.assert_called_once()
    forwarded = event_listener.listen.call_args[0][0]
    assert forwarded[:2] == BLE_PREPEND
    assert forwarded[2:] == bytes(payload)


def test_on_notify_result_is_bytes():
    gw, event_listener = _make_gw()
    gw._on_notify(None, bytearray(18))
    forwarded = event_listener.listen.call_args[0][0]
    assert isinstance(forwarded, bytes)


# ── _ble_main ─────────────────────────────────────────────────────────────────


def test_ble_main_sleeps_when_not_connected():
    """_ble_main exits its poll loop on _stop without calling _find_peripheral_by_wpid."""
    gw, _ = _make_gw()
    gw._connected = False

    sleep_count = [0]

    async def run():
        async def fake_sleep(t):
            sleep_count[0] += 1
            gw._stop.set()

        with patch("cleverswitch.gateway.hid_gateway_ble.asyncio.sleep", side_effect=fake_sleep):
            with patch.object(gw, "_find_peripheral_by_wpid", new_callable=AsyncMock) as find_mock:
                await gw._ble_main()
                find_mock.assert_not_called()

    asyncio.run(run())
    assert sleep_count[0] == 1


def test_ble_main_finds_peripheral_when_connected():
    gw, _ = _make_gw()
    gw._connected = True

    calls = [0]

    async def run():
        mock_device = MagicMock()

        async def fake_find(wpid):
            calls[0] += 1
            gw._stop.set()
            return None

        with patch.object(gw, "_find_peripheral_by_wpid", side_effect=fake_find):
            with patch("cleverswitch.gateway.hid_gateway_ble.asyncio.sleep", new_callable=AsyncMock):
                await gw._ble_main()

    asyncio.run(run())
    assert calls[0] == 1


def test_ble_main_calls_connect_and_listen_when_peripheral_found():
    gw, _ = _make_gw()
    gw._connected = True

    connect_calls = [0]

    async def run():
        mock_device = MagicMock()

        async def fake_find(wpid):
            return mock_device

        async def fake_connect(device):
            connect_calls[0] += 1
            gw._stop.set()

        with patch.object(gw, "_find_peripheral_by_wpid", side_effect=fake_find):
            with patch.object(gw, "_connect_and_listen", side_effect=fake_connect):
                await gw._ble_main()

    asyncio.run(run())
    assert connect_calls[0] == 1


def test_ble_main_sleeps_on_exception():
    gw, _ = _make_gw()
    gw._connected = True

    sleep_calls = [0]

    async def run():
        async def fake_find(wpid):
            raise RuntimeError("BLE stack error")

        async def fake_sleep(t):
            sleep_calls[0] += 1
            gw._stop.set()

        with patch.object(gw, "_find_peripheral_by_wpid", side_effect=fake_find):
            with patch("cleverswitch.gateway.hid_gateway_ble.asyncio.sleep", side_effect=fake_sleep):
                await gw._ble_main()

    asyncio.run(run())
    assert sleep_calls[0] == 1


# ── _connect_and_listen ───────────────────────────────────────────────────────


def test_connect_and_listen_subscribes_to_notify_characteristic():
    gw, event_listener = _make_gw()
    gw._connected = True

    mock_client = MagicMock()
    mock_client.start_notify = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    async def run():
        gw._stop.set()  # exit the inner while immediately

        with patch("cleverswitch.gateway.hid_gateway_ble.BleakClient", return_value=mock_client):
            await gw._connect_and_listen(MagicMock())

    asyncio.run(run())
    mock_client.start_notify.assert_called_once()
    char_uuid = mock_client.start_notify.call_args[0][0]
    assert "00010001" in char_uuid


def test_connect_and_listen_disconnected_callback_calls_set_connected_false():
    """disconnected_callback must call _set_connected(False), not assign directly."""
    gw, event_listener = _make_gw()
    gw._connected = True

    captured_callback = [None]

    mock_client = MagicMock()
    mock_client.start_notify = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    def fake_bleak_client(device, disconnected_callback=None, **kwargs):
        captured_callback[0] = disconnected_callback
        return mock_client

    async def run():
        gw._stop.set()

        with patch("cleverswitch.gateway.hid_gateway_ble.BleakClient", side_effect=fake_bleak_client):
            await gw._connect_and_listen(MagicMock())

    asyncio.run(run())

    assert captured_callback[0] is not None

    # Invoke the callback — it must call _set_connected(False)
    with patch.object(gw, "_set_connected") as mock_set:
        captured_callback[0](mock_client)
        mock_set.assert_called_once_with(False)


def test_connect_and_listen_disconnected_callback_synthesizes_0x41_disconnect_event():
    """_set_connected(False) triggers the inherited HidGatewayBT path that calls event_listener.listen."""
    gw, event_listener = _make_gw(pid=0xB023)
    gw._connected = True

    captured_callback = [None]

    mock_client = MagicMock()
    mock_client.start_notify = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    def fake_bleak_client(device, disconnected_callback=None, **kwargs):
        captured_callback[0] = disconnected_callback
        return mock_client

    async def run():
        gw._stop.set()

        with patch("cleverswitch.gateway.hid_gateway_ble.BleakClient", side_effect=fake_bleak_client):
            await gw._connect_and_listen(MagicMock())

    asyncio.run(run())

    # Reset listen call count to isolate the callback effect
    event_listener.listen.reset_mock()
    captured_callback[0](mock_client)

    # HidGatewayBT._set_connected calls event_listener.listen with the 0x41 bytes
    event_listener.listen.assert_called_once()
    raw = event_listener.listen.call_args[0][0]
    assert raw[2] == 0x41  # Device Connection opcode
    assert (raw[4] & 0x40) == 0x40  # bit 6 set → disconnected


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
    event_listener.listen.assert_not_called()

    # Subscribe — main thread should wake up and fire 0x41
    gw._ble_subscribed.set()
    assert fired.wait(timeout=2.0) is True
    event_listener.listen.assert_called_once()
    raw = event_listener.listen.call_args[0][0]
    assert raw[2] == 0x41
    assert (raw[4] & 0x40) == 0x00  # connected


def test_set_connected_true_fires_immediately_when_ble_not_ok(mocker):
    mocker.patch("cleverswitch.gateway.hid_gateway_ble._BLE_OK", False)
    gw, event_listener = _make_gw()

    gw._set_connected(True)

    assert gw._connected is True
    event_listener.listen.assert_called_once()
    raw = event_listener.listen.call_args[0][0]
    assert raw[2] == 0x41
    assert (raw[4] & 0x40) == 0x00  # connected


def test_set_connected_true_does_not_fire_if_stop_set_during_wait(mocker):
    mocker.patch("cleverswitch.gateway.hid_gateway_ble._BLE_OK", True)
    gw, event_listener = _make_gw()

    fired = threading.Event()

    def call_set_connected():
        gw._set_connected(True)
        fired.set()

    t = threading.Thread(target=call_set_connected, daemon=True)
    t.start()

    # Don't set _ble_subscribed; trigger shutdown instead
    assert fired.wait(timeout=0.3) is False
    gw._stop.set()

    assert fired.wait(timeout=2.0) is True
    event_listener.listen.assert_not_called()


def test_set_connected_false_clears_ble_subscribed_and_fires_disconnect(mocker):
    mocker.patch("cleverswitch.gateway.hid_gateway_ble._BLE_OK", True)
    gw, event_listener = _make_gw()
    gw._connected = True
    gw._ble_subscribed.set()

    gw._set_connected(False)

    assert gw._connected is False
    assert not gw._ble_subscribed.is_set()
    event_listener.listen.assert_called_once()
    raw = event_listener.listen.call_args[0][0]
    assert raw[2] == 0x41
    assert (raw[4] & 0x40) == 0x40  # disconnected


def test_connect_and_listen_sets_ble_subscribed_event():
    gw, _ = _make_gw()
    gw._connected = True
    assert not gw._ble_subscribed.is_set()

    mock_client = MagicMock()
    mock_client.start_notify = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    async def run():
        gw._stop.set()
        with patch("cleverswitch.gateway.hid_gateway_ble.BleakClient", return_value=mock_client):
            await gw._connect_and_listen(MagicMock())

    asyncio.run(run())
    assert gw._ble_subscribed.is_set()


# ── _find_peripheral_by_wpid ─────────────────────────────────────────────────


def test_find_peripheral_by_wpid_returns_matching_device():
    gw, _ = _make_gw(pid=0xB023)

    target_wpid = 0xB023
    # PnP ID: bytes [3:5] little-endian = 0xB023
    pnp_bytes = bytearray([0x01, 0x6D, 0x04, 0x23, 0xB0, 0x00, 0x00])

    mock_peripheral = MagicMock()
    mock_peripheral.identifier.return_value.UUIDString.return_value = "UUID-1"
    mock_peripheral.name.return_value = "MX Keys"

    mock_delegate = MagicMock()
    mock_delegate.wait_until_ready = AsyncMock()
    mock_delegate.central_manager.retrieveConnectedPeripheralsWithServices_.return_value = [mock_peripheral]

    mock_probe = MagicMock()
    mock_probe.read_gatt_char = AsyncMock(return_value=pnp_bytes)
    mock_probe.__aenter__ = AsyncMock(return_value=mock_probe)
    mock_probe.__aexit__ = AsyncMock(return_value=False)

    mock_ble_device = MagicMock()
    mock_ble_device.address = "UUID-1"

    async def run():
        with patch("cleverswitch.gateway.hid_gateway_ble.CentralManagerDelegate", return_value=mock_delegate):
            with patch("cleverswitch.gateway.hid_gateway_ble.CBUUID"):
                with patch("cleverswitch.gateway.hid_gateway_ble.BLEDevice", return_value=mock_ble_device):
                    with patch("cleverswitch.gateway.hid_gateway_ble.BleakClient", return_value=mock_probe):
                        result = await gw._find_peripheral_by_wpid(target_wpid)
        return result

    result = asyncio.run(run())
    assert result is mock_ble_device


def test_find_peripheral_by_wpid_returns_none_when_no_match():
    gw, _ = _make_gw(pid=0xB023)

    # PnP ID: bytes [3:5] = 0xB024 — wrong device
    pnp_bytes = bytearray([0x01, 0x6D, 0x04, 0x24, 0xB0, 0x00, 0x00])

    mock_peripheral = MagicMock()
    mock_peripheral.identifier.return_value.UUIDString.return_value = "UUID-2"
    mock_peripheral.name.return_value = "Other Device"

    mock_delegate = MagicMock()
    mock_delegate.wait_until_ready = AsyncMock()
    mock_delegate.central_manager.retrieveConnectedPeripheralsWithServices_.return_value = [mock_peripheral]

    mock_probe = MagicMock()
    mock_probe.read_gatt_char = AsyncMock(return_value=pnp_bytes)
    mock_probe.__aenter__ = AsyncMock(return_value=mock_probe)
    mock_probe.__aexit__ = AsyncMock(return_value=False)

    mock_ble_device = MagicMock()
    mock_ble_device.address = "UUID-2"

    async def run():
        with patch("cleverswitch.gateway.hid_gateway_ble.CentralManagerDelegate", return_value=mock_delegate):
            with patch("cleverswitch.gateway.hid_gateway_ble.CBUUID"):
                with patch("cleverswitch.gateway.hid_gateway_ble.BLEDevice", return_value=mock_ble_device):
                    with patch("cleverswitch.gateway.hid_gateway_ble.BleakClient", return_value=mock_probe):
                        result = await gw._find_peripheral_by_wpid(0xB023)
        return result

    result = asyncio.run(run())
    assert result is None


def test_find_peripheral_by_wpid_returns_none_when_no_candidates():
    gw, _ = _make_gw()

    mock_delegate = MagicMock()
    mock_delegate.wait_until_ready = AsyncMock()
    mock_delegate.central_manager.retrieveConnectedPeripheralsWithServices_.return_value = []

    async def run():
        with patch("cleverswitch.gateway.hid_gateway_ble.CentralManagerDelegate", return_value=mock_delegate):
            with patch("cleverswitch.gateway.hid_gateway_ble.CBUUID"):
                result = await gw._find_peripheral_by_wpid(0xB023)
        return result

    result = asyncio.run(run())
    assert result is None


def test_find_peripheral_by_wpid_skips_probe_exception():
    """When PnP probe raises, that candidate is skipped and None is returned."""
    gw, _ = _make_gw(pid=0xB023)

    mock_peripheral = MagicMock()
    mock_peripheral.identifier.return_value.UUIDString.return_value = "UUID-3"
    mock_peripheral.name.return_value = "Failing Device"

    mock_delegate = MagicMock()
    mock_delegate.wait_until_ready = AsyncMock()
    mock_delegate.central_manager.retrieveConnectedPeripheralsWithServices_.return_value = [mock_peripheral]

    mock_probe = MagicMock()
    mock_probe.read_gatt_char = AsyncMock(side_effect=Exception("BT error"))
    mock_probe.__aenter__ = AsyncMock(return_value=mock_probe)
    mock_probe.__aexit__ = AsyncMock(return_value=False)

    mock_ble_device = MagicMock()
    mock_ble_device.address = "UUID-3"

    async def run():
        with patch("cleverswitch.gateway.hid_gateway_ble.CentralManagerDelegate", return_value=mock_delegate):
            with patch("cleverswitch.gateway.hid_gateway_ble.CBUUID"):
                with patch("cleverswitch.gateway.hid_gateway_ble.BLEDevice", return_value=mock_ble_device):
                    with patch("cleverswitch.gateway.hid_gateway_ble.BleakClient", return_value=mock_probe):
                        result = await gw._find_peripheral_by_wpid(0xB023)
        return result

    result = asyncio.run(run())
    assert result is None
