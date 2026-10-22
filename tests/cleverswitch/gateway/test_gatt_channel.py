"""Unit tests for gateway/gatt_channel.py."""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cleverswitch.gateway import gatt_channel
from cleverswitch.gateway.gatt_channel import BLE_PREPEND, GattChannel

KEYBOARD_PNP = bytearray([0x02, 0x6D, 0x04, 0x5B, 0xB3, 0x13, 0x00])  # wpid 0xB35B
MOUSE_PNP = bytearray([0x02, 0x6D, 0x04, 0x23, 0xB0, 0x13, 0x00])  # wpid 0xB023


def _make_channel(pid=0xB023):
    on_report = MagicMock()
    channel = GattChannel(pid, on_report, MagicMock(), threading.Event())
    return channel, on_report


def _bleak_client(connected=True):
    client = MagicMock()
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.start_notify = AsyncMock()
    client.is_connected = connected
    return client


async def _no_sleep(_t):
    await asyncio.sleep(0)


# ── activation ───────────────────────────────────────────────────────────────


def test_activate_and_deactivate_toggle_the_channel():
    ch, _ = _make_channel()
    assert not ch._active.is_set()
    ch.activate()
    assert ch._active.is_set()
    ch.deactivate()
    assert not ch._active.is_set()


# ── _on_notify ───────────────────────────────────────────────────────────────


def test_on_notify_prepends_ble_prepend_and_forwards_report():
    ch, on_report = _make_channel()
    payload = bytearray([0x11, 0x01, 0x02, 0x03] + [0x00] * 14)

    ch._on_notify(None, payload)

    on_report.assert_called_once_with(BLE_PREPEND + bytes(payload))


# ── _main ────────────────────────────────────────────────────────────────────


def test_main_idles_while_inactive():
    ch, _ = _make_channel()

    async def fake_sleep(_t):
        ch._stop.set()

    async def run():
        with patch("cleverswitch.gateway.gatt_channel.asyncio.sleep", side_effect=fake_sleep):
            with patch.object(ch, "_find_peripheral_by_wpid", new_callable=AsyncMock) as find:
                await ch._main()
                find.assert_not_called()

    asyncio.run(run())


def test_main_connects_when_active_and_peripheral_found():
    ch, _ = _make_channel()
    ch.activate()
    device = MagicMock()

    async def fake_connect(_device):
        ch._stop.set()

    async def run():
        with patch.object(ch, "_find_peripheral_by_wpid", AsyncMock(return_value=device)):
            with patch.object(ch, "_connect_and_listen", side_effect=fake_connect) as connect:
                await ch._main()
                connect.assert_called_once_with(device)

    asyncio.run(run())


def test_main_logs_missing_peripheral_once_per_activation(caplog):
    import logging

    ch, _ = _make_channel()
    ch.activate()
    lookups = [0]

    async def fake_find(_wpid):
        lookups[0] += 1
        if lookups[0] == 3:
            ch._stop.set()
        return None

    async def run():
        with patch.object(ch, "_find_peripheral_by_wpid", side_effect=fake_find):
            with patch("cleverswitch.gateway.gatt_channel.asyncio.sleep", AsyncMock()):
                await ch._main()

    with caplog.at_level(logging.DEBUG):
        asyncio.run(run())

    assert lookups[0] == 3
    assert sum("No GATT peripheral" in r.message for r in caplog.records) == 1


def test_main_survives_lookup_errors():
    ch, _ = _make_channel()
    ch.activate()
    sleeps = [0]

    async def fake_find(_wpid):
        raise RuntimeError("BLE stack error")

    async def fake_sleep(_t):
        sleeps[0] += 1
        ch._stop.set()

    async def run():
        with patch.object(ch, "_find_peripheral_by_wpid", side_effect=fake_find):
            with patch("cleverswitch.gateway.gatt_channel.asyncio.sleep", side_effect=fake_sleep):
                await ch._main()

    asyncio.run(run())
    assert sleeps[0] == 1


# ── _connect_and_listen ──────────────────────────────────────────────────────


def _listen(ch, client, during=None):
    """Run one session; `during` runs on the first poll of the listen loop."""
    polls = [0]

    async def fake_sleep(_t):
        polls[0] += 1
        if during is not None and polls[0] == 1:
            during()
        if polls[0] > 3:
            ch._stop.set()

    async def run():
        with patch("cleverswitch.gateway.gatt_channel.BleakClient", return_value=client) as cls:
            with patch("cleverswitch.gateway.gatt_channel.asyncio.sleep", side_effect=fake_sleep):
                await ch._connect_and_listen(MagicMock())
        return cls

    return asyncio.run(run())


def test_session_subscribes_to_the_hidpp_characteristic():
    ch, _ = _make_channel()
    ch.activate()
    client = _bleak_client()

    _listen(ch, client)

    client.connect.assert_awaited_once()
    assert client.start_notify.call_args[0][0] == gatt_channel.LOGI_HIDPP_CHAR


def test_session_is_live_while_subscribed():
    ch, _ = _make_channel()
    ch.activate()
    seen = []

    _listen(ch, _bleak_client(), during=lambda: seen.append((ch.subscribed.is_set(), ch._client is not None)))

    assert seen == [(True, True)]
    assert not ch.subscribed.is_set()
    assert ch._client is None


def test_session_ends_when_deactivated():
    ch, _ = _make_channel()
    ch.activate()
    client = _bleak_client()

    _listen(ch, client, during=ch.deactivate)

    client.disconnect.assert_awaited_once()
    ch._on_state.assert_called_once_with(True)  # HID went away; nothing to re-arm


def test_shutdown_reports_no_drop():
    """A re-arm during shutdown would re-divert keys that shutdown just un-diverted."""
    ch, _ = _make_channel()
    ch.activate()

    _listen(ch, _bleak_client(), during=ch._stop.set)

    ch._on_state.assert_called_once_with(True)


def test_session_ends_when_drop_callback_fires():
    ch, _ = _make_channel()
    ch.activate()
    client = _bleak_client()
    holder = {}

    def capture(_device, disconnected_callback=None):
        holder["cb"] = disconnected_callback
        return client

    async def fake_sleep(_t):
        holder["cb"](client)

    async def run():
        with patch("cleverswitch.gateway.gatt_channel.BleakClient", side_effect=capture):
            with patch("cleverswitch.gateway.gatt_channel.asyncio.sleep", side_effect=fake_sleep):
                await ch._connect_and_listen(MagicMock())

    asyncio.run(run())

    assert not ch._stop.is_set()
    assert [c.args for c in ch._on_state.call_args_list] == [(True,), (False,)]


def test_session_ends_when_client_reports_disconnected_without_callback():
    """Bluetooth powered off mid-session: CoreBluetooth never fires the drop callback."""
    ch, _ = _make_channel()
    ch.activate()
    client = _bleak_client()

    def power_off():
        client.is_connected = False

    _listen(ch, client, during=power_off)

    assert not ch._stop.is_set()
    assert [c.args for c in ch._on_state.call_args_list] == [(True,), (False,)]


def test_session_drop_never_touches_anything_but_its_own_state():
    ch, on_report = _make_channel()
    ch.activate()

    _listen(ch, _bleak_client(), during=ch.deactivate)

    on_report.assert_not_called()
    assert not ch._stop.is_set()


def test_failed_subscribe_reports_no_state_and_disconnects():
    ch, _ = _make_channel()
    ch.activate()
    client = _bleak_client()
    client.start_notify.side_effect = RuntimeError("no such characteristic")

    with pytest.raises(RuntimeError):
        _listen(ch, client)

    ch._on_state.assert_not_called()
    client.disconnect.assert_awaited_once()


def test_hung_disconnect_is_abandoned_after_timeout(mocker):
    mocker.patch("cleverswitch.gateway.gatt_channel._DISCONNECT_TIMEOUT", 0.01)
    ch, _ = _make_channel()
    client = _bleak_client()

    async def never_confirms():
        await asyncio.Event().wait()

    client.disconnect.side_effect = never_confirms

    asyncio.run(asyncio.wait_for(ch._disconnect(client), 1.0))  # must not hang


# ── _find_peripheral_by_wpid ─────────────────────────────────────────────────


def _peripheral(uuid):
    cb = MagicMock()
    cb.identifier.return_value.UUIDString.return_value = uuid
    cb.name.return_value = uuid
    return cb


def _ble_device(uuid, _name, _details):
    device = MagicMock()
    device.address = uuid
    return device


def _find(ch, peripherals, pnp_by_uuid, delegate=None):
    delegate = delegate or MagicMock()
    delegate.wait_until_ready = AsyncMock()
    delegate.central_manager.retrieveConnectedPeripheralsWithServices_.return_value = peripherals
    probed = []

    def make_client(device):
        probed.append(device.address)
        client = _bleak_client()
        pnp = pnp_by_uuid.get(device.address)
        client.read_gatt_char = AsyncMock(return_value=pnp, side_effect=None if pnp else Exception("BT error"))
        return client

    async def run():
        with (
            patch("cleverswitch.gateway.gatt_channel.CentralManagerDelegate", return_value=delegate) as delegate_cls,
            patch("cleverswitch.gateway.gatt_channel.CBUUID"),
            patch("cleverswitch.gateway.gatt_channel.BLEDevice", side_effect=_ble_device),
            patch("cleverswitch.gateway.gatt_channel.BleakClient", side_effect=make_client),
        ):
            result = await ch._find_peripheral_by_wpid(ch._pid)
        return result, probed, delegate_cls

    return asyncio.run(run())


def test_find_returns_the_peripheral_whose_pnp_matches():
    ch, _ = _make_channel(pid=0xB023)
    result, _, _ = _find(ch, [_peripheral("KB"), _peripheral("MOUSE")], {"KB": KEYBOARD_PNP, "MOUSE": MOUSE_PNP})
    assert result.address == "MOUSE"


def test_find_returns_none_when_nothing_matches():
    ch, _ = _make_channel(pid=0xB023)
    result, _, _ = _find(ch, [_peripheral("KB")], {"KB": KEYBOARD_PNP})
    assert result is None


def test_find_returns_none_without_candidates():
    ch, _ = _make_channel()
    result, probed, _ = _find(ch, [], {})
    assert result is None
    assert probed == []


def test_find_skips_a_failing_probe():
    ch, _ = _make_channel(pid=0xB023)
    result, _, _ = _find(ch, [_peripheral("BROKEN"), _peripheral("MOUSE")], {"MOUSE": MOUSE_PNP})
    assert result.address == "MOUSE"


def test_find_remembers_the_match_and_skips_probing_next_time():
    ch, _ = _make_channel(pid=0xB023)
    peripherals = [_peripheral("KB"), _peripheral("MOUSE")]
    pnp = {"KB": KEYBOARD_PNP, "MOUSE": MOUSE_PNP}
    _find(ch, peripherals, pnp)

    result, probed, _ = _find(ch, peripherals, pnp, delegate=ch._delegate)

    assert result.address == "MOUSE"
    assert probed == []


def test_find_reuses_one_central_manager_delegate():
    ch, _ = _make_channel(pid=0xB023)
    _find(ch, [], {})
    first = ch._delegate

    _, _, delegate_cls = _find(ch, [], {}, delegate=first)

    assert ch._delegate is first
    delegate_cls.assert_not_called()


def test_probe_always_disconnects():
    ch, _ = _make_channel(pid=0xB023)
    client = _bleak_client()
    client.read_gatt_char = AsyncMock(return_value=MOUSE_PNP)

    async def run():
        with patch("cleverswitch.gateway.gatt_channel.BleakClient", return_value=client):
            return await ch._probe_wpid(MagicMock())

    assert asyncio.run(run()) == 0xB023
    client.disconnect.assert_awaited_once()


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
