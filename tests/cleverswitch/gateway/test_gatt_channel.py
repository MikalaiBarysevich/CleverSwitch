"""Unit tests for gateway/gatt_channel.py."""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

from cleverswitch.gateway.gatt_channel import BLE_PREPEND, GattChannel


def _make_channel(pid=0xB023):
    on_report = MagicMock()
    channel = GattChannel(pid, on_report, threading.Event(), MagicMock(), threading.Event())
    return channel, on_report


def test_on_notify_prepends_ble_prepend_and_forwards_to_listener():
    ch, on_report = _make_channel()
    payload = bytearray([0x11, 0x01, 0x02, 0x03] + [0x00] * 14)
    ch._on_notify(None, payload)

    on_report.assert_called_once()
    forwarded = on_report.call_args[0][0]
    assert forwarded[:2] == BLE_PREPEND
    assert forwarded[2:] == bytes(payload)


def test_on_notify_result_is_bytes():
    ch, on_report = _make_channel()
    ch._on_notify(None, bytearray(18))
    forwarded = on_report.call_args[0][0]
    assert isinstance(forwarded, bytes)


def test_main_sleeps_when_not_connected():
    """_main exits its poll loop on _stop without calling _find_peripheral_by_wpid."""
    ch, _ = _make_channel()
    ch._link_up.clear()

    sleep_count = [0]

    async def run():
        async def fake_sleep(t):
            sleep_count[0] += 1
            ch._stop.set()

        with patch("cleverswitch.gateway.gatt_channel.asyncio.sleep", side_effect=fake_sleep):
            with patch.object(ch, "_find_peripheral_by_wpid", new_callable=AsyncMock) as find_mock:
                await ch._main()
                find_mock.assert_not_called()

    asyncio.run(run())
    assert sleep_count[0] == 1


def test_main_finds_peripheral_when_connected():
    ch, _ = _make_channel()
    ch._link_up.set()

    calls = [0]

    async def run():
        async def fake_find(wpid):
            calls[0] += 1
            ch._stop.set()
            return None

        with patch.object(ch, "_find_peripheral_by_wpid", side_effect=fake_find):
            with patch("cleverswitch.gateway.gatt_channel.asyncio.sleep", new_callable=AsyncMock):
                await ch._main()

    asyncio.run(run())
    assert calls[0] == 1


def test_main_calls_connect_and_listen_when_peripheral_found():
    ch, _ = _make_channel()
    ch._link_up.set()

    connect_calls = [0]

    async def run():
        mock_device = MagicMock()

        async def fake_find(wpid):
            return mock_device

        async def fake_connect(device):
            connect_calls[0] += 1
            ch._stop.set()

        with patch.object(ch, "_find_peripheral_by_wpid", side_effect=fake_find):
            with patch.object(ch, "_connect_and_listen", side_effect=fake_connect):
                await ch._main()

    asyncio.run(run())
    assert connect_calls[0] == 1


def test_main_sleeps_on_exception():
    ch, _ = _make_channel()
    ch._link_up.set()

    sleep_calls = [0]

    async def run():
        async def fake_find(wpid):
            raise RuntimeError("BLE stack error")

        async def fake_sleep(t):
            sleep_calls[0] += 1
            ch._stop.set()

        with patch.object(ch, "_find_peripheral_by_wpid", side_effect=fake_find):
            with patch("cleverswitch.gateway.gatt_channel.asyncio.sleep", side_effect=fake_sleep):
                await ch._main()

    asyncio.run(run())
    assert sleep_calls[0] == 1


def test_connect_and_listen_subscribes_to_notify_characteristic():
    ch, on_report = _make_channel()
    ch._link_up.set()

    mock_client = MagicMock()
    mock_client.start_notify = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    async def run():
        ch._stop.set()  # exit the inner while immediately

        with patch("cleverswitch.gateway.gatt_channel.BleakClient", return_value=mock_client):
            await ch._connect_and_listen(MagicMock())

    asyncio.run(run())
    mock_client.start_notify.assert_called_once()
    char_uuid = mock_client.start_notify.call_args[0][0]
    assert "00010001" in char_uuid


def test_connect_and_listen_disconnected_callback_reports_drop():
    """A GATT drop is reported to the owner, which decides what it means for the link."""
    ch, on_report = _make_channel()
    ch._link_up.set()

    captured_callback = [None]

    mock_client = MagicMock()
    mock_client.start_notify = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    def fake_bleak_client(device, disconnected_callback=None, **kwargs):
        captured_callback[0] = disconnected_callback
        return mock_client

    async def run():
        ch._stop.set()

        with patch("cleverswitch.gateway.gatt_channel.BleakClient", side_effect=fake_bleak_client):
            await ch._connect_and_listen(MagicMock())

    asyncio.run(run())

    assert captured_callback[0] is not None

    captured_callback[0](mock_client)
    ch._on_drop.assert_called_once_with()


def test_connect_and_listen_setssubscribed_event():
    ch, _ = _make_channel()
    ch._link_up.set()
    assert not ch.subscribed.is_set()

    mock_client = MagicMock()
    mock_client.start_notify = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    async def run():
        ch._stop.set()
        with patch("cleverswitch.gateway.gatt_channel.BleakClient", return_value=mock_client):
            await ch._connect_and_listen(MagicMock())

    asyncio.run(run())
    assert ch.subscribed.is_set()


def test_find_peripheral_by_wpid_returns_matching_device():
    ch, _ = _make_channel(pid=0xB023)

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
        with patch("cleverswitch.gateway.gatt_channel.CentralManagerDelegate", return_value=mock_delegate):
            with patch("cleverswitch.gateway.gatt_channel.CBUUID"):
                with patch("cleverswitch.gateway.gatt_channel.BLEDevice", return_value=mock_ble_device):
                    with patch("cleverswitch.gateway.gatt_channel.BleakClient", return_value=mock_probe):
                        result = await ch._find_peripheral_by_wpid(target_wpid)
        return result

    result = asyncio.run(run())
    assert result is mock_ble_device


def test_find_peripheral_by_wpid_returns_none_when_no_match():
    ch, _ = _make_channel(pid=0xB023)

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
        with patch("cleverswitch.gateway.gatt_channel.CentralManagerDelegate", return_value=mock_delegate):
            with patch("cleverswitch.gateway.gatt_channel.CBUUID"):
                with patch("cleverswitch.gateway.gatt_channel.BLEDevice", return_value=mock_ble_device):
                    with patch("cleverswitch.gateway.gatt_channel.BleakClient", return_value=mock_probe):
                        result = await ch._find_peripheral_by_wpid(0xB023)
        return result

    result = asyncio.run(run())
    assert result is None


def test_find_peripheral_by_wpid_returns_none_when_no_candidates():
    ch, _ = _make_channel()

    mock_delegate = MagicMock()
    mock_delegate.wait_until_ready = AsyncMock()
    mock_delegate.central_manager.retrieveConnectedPeripheralsWithServices_.return_value = []

    async def run():
        with patch("cleverswitch.gateway.gatt_channel.CentralManagerDelegate", return_value=mock_delegate):
            with patch("cleverswitch.gateway.gatt_channel.CBUUID"):
                result = await ch._find_peripheral_by_wpid(0xB023)
        return result

    result = asyncio.run(run())
    assert result is None


def test_find_peripheral_by_wpid_skips_probe_exception():
    """When PnP probe raises, that candidate is skipped and None is returned."""
    ch, _ = _make_channel(pid=0xB023)

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
        with patch("cleverswitch.gateway.gatt_channel.CentralManagerDelegate", return_value=mock_delegate):
            with patch("cleverswitch.gateway.gatt_channel.CBUUID"):
                with patch("cleverswitch.gateway.gatt_channel.BLEDevice", return_value=mock_ble_device):
                    with patch("cleverswitch.gateway.gatt_channel.BleakClient", return_value=mock_probe):
                        result = await ch._find_peripheral_by_wpid(0xB023)
        return result

    result = asyncio.run(run())
    assert result is None


# ── write: ATT write mode (issue #109) ───────────────────────────────────────


def _ready_channel():
    ch, _ = _make_channel()
    client = MagicMock()
    client.write_gatt_char = MagicMock()
    ch._client = client
    ch._loop = MagicMock()
    return ch, client


def test_write_uses_write_with_response():
    """Write-without-response is silently dropped when macOS has no credit; bleak never checks."""
    ch, client = _ready_channel()

    with patch("cleverswitch.gateway.gatt_channel.asyncio.run_coroutine_threadsafe") as run_threadsafe:
        run_threadsafe.return_value.result.return_value = None
        assert ch.write(bytes.fromhex("11ff083e00d10000000300000000000000000000")) is True

    client.write_gatt_char.assert_called_once()
    assert client.write_gatt_char.call_args.kwargs["response"] is True


def test_write_strips_the_two_byte_hidpp_prefix():
    ch, client = _ready_channel()
    msg = bytes.fromhex("11ff083e00d10000000300000000000000000000")

    with patch("cleverswitch.gateway.gatt_channel.asyncio.run_coroutine_threadsafe") as run_threadsafe:
        run_threadsafe.return_value.result.return_value = None
        ch.write(msg)

    assert client.write_gatt_char.call_args[0][1] == msg[2:]


def test_write_returns_false_when_gatt_write_fails():
    """A characteristic without the write property must not silently lose the message."""
    ch, _ = _ready_channel()

    with patch(
        "cleverswitch.gateway.gatt_channel.asyncio.run_coroutine_threadsafe",
        side_effect=Exception("write not permitted"),
    ):
        assert ch.write(b"\x11\xff\x08\x3e") is False


def test_write_without_client_logs_and_returns_false(caplog):
    """The silent HID fallback hid reconnect races — every write must name its transport."""
    import logging

    ch, _ = _make_channel()

    with caplog.at_level(logging.DEBUG):
        assert ch.write(b"\x11\xff\x08\x3e") is False

    assert any("BLE client not ready" in r.message for r in caplog.records)


def test_write_logs_gatt_transport_on_success(caplog):
    import logging

    ch, client = _ready_channel()

    with caplog.at_level(logging.DEBUG):
        with patch("cleverswitch.gateway.gatt_channel.asyncio.run_coroutine_threadsafe") as run_threadsafe:
            run_threadsafe.return_value.result.return_value = None
            ch.write(b"\x11\xff\x08\x3e")

    assert any("Wrote via GATT" in r.message for r in caplog.records)
    client.write_gatt_char.assert_called_once()


def test_start_runs_the_loop_on_a_daemon_thread(mocker):
    thread_cls = mocker.patch("cleverswitch.gateway.gatt_channel.Thread")
    ch, _ = _make_channel()

    ch.start()

    assert thread_cls.call_args.kwargs == {"target": ch._run_loop, "daemon": True}
    thread_cls.return_value.start.assert_called_once()


def test_run_loop_clears_loop_reference_on_exit():
    ch, _ = _make_channel()
    ch._stop.set()

    ch._run_loop()

    assert ch._loop is None
