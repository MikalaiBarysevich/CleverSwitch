"""Unit tests for gateway/hid_gateway.py and gateway/hid_gateway_bt.py."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

from cleverswitch.errors.errors import TransportError
from cleverswitch.event.transport_disconnected_event import TransportDisconnectedEvent
from cleverswitch.event.write_event import WriteEvent
from cleverswitch.gateway.hid_gateway import _RECONNECT_BACKOFF_MAX, _RECONNECT_BACKOFF_MIN, HidGateway
from cleverswitch.gateway.hid_gateway_bt import HidGatewayBT
from cleverswitch.hidpp.constants import BOLT_PID, REPORT_LONG
from cleverswitch.hidpp.transport import HidDeviceInfo
from cleverswitch.listener.event_listener import EventListener


def _device_info(pid=BOLT_PID, connection_type="receiver"):
    return HidDeviceInfo(
        path=b"/dev/hidraw0", vid=0x046D, pid=pid, usage_page=0xFF00, usage=0x0002, connection_type=connection_type
    )


def _bt_device_info(pid=0xB023):
    return HidDeviceInfo(
        path=b"/dev/hidraw1", vid=0x046D, pid=pid, usage_page=0xFF43, usage=0x0202, connection_type="bluetooth"
    )


# ── HidGateway.notify ────────────────────────────────────────────────────────


def test_notify_ignores_non_write_event():
    event_listener = MagicMock(spec=EventListener)
    gw = HidGateway(_device_info(), event_listener)
    gw.notify("not a WriteEvent")  # must not raise


def test_notify_ignores_wrong_pid():
    event_listener = MagicMock(spec=EventListener)
    gw = HidGateway(_device_info(pid=BOLT_PID), event_listener)
    event = WriteEvent(slot=1, pid=0x9999, hid_message=b"\x11" + bytes(19))
    gw.notify(event)  # must not raise (different pid)


def test_notify_drops_write_when_disconnected_and_was_previously_connected():
    event_listener = MagicMock(spec=EventListener)
    gw = HidGateway(_device_info(), event_listener)
    gw._connected = False
    gw._ever_connected = True
    mock_transport = MagicMock()
    gw._transport = mock_transport

    event = WriteEvent(slot=1, pid=BOLT_PID, hid_message=b"\x11" + bytes(19))
    gw.notify(event)

    mock_transport.write.assert_not_called()


def test_notify_writes_when_connected():
    event_listener = MagicMock(spec=EventListener)
    gw = HidGateway(_device_info(), event_listener)
    gw._connected = True
    gw._ever_connected = True
    mock_transport = MagicMock()
    gw._transport = mock_transport

    msg = bytes([REPORT_LONG]) + bytes(19)
    event = WriteEvent(slot=1, pid=BOLT_PID, hid_message=msg)
    gw.notify(event)

    mock_transport.write.assert_called_once_with(msg)


def test_notify_drops_write_when_never_connected_and_grace_expired():
    """Regression guard for #92: a collection that never connects must not park the drain thread.

    HidGateway.notify runs on the write topic's per-subscriber drain thread. The old code spun
    `while not self._connected` forever when _ever_connected was False, so the queue behind it grew
    without bound. The wait is now capped by a one-shot grace window measured from construction.
    """
    event_listener = MagicMock(spec=EventListener)
    gw = HidGateway(_device_info(), event_listener)
    gw._connected = False
    gw._ever_connected = False
    gw._grace_deadline = time.monotonic() - 1.0
    mock_transport = MagicMock()
    gw._transport = mock_transport

    event = WriteEvent(slot=1, pid=BOLT_PID, hid_message=b"\x11" + bytes(19))
    # Run on a worker so a reintroduced spin fails the test instead of hanging the suite.
    worker = threading.Thread(target=gw.notify, args=(event,), daemon=True)
    worker.start()
    worker.join(timeout=2.0)

    assert not worker.is_alive(), "notify must return once the first-connect grace has expired"
    mock_transport.write.assert_not_called()


def test_notify_within_grace_writes_once_gateway_connects():
    event_listener = MagicMock(spec=EventListener)
    gw = HidGateway(_device_info(), event_listener)
    gw._connected = False
    gw._ever_connected = False
    gw._grace_deadline = time.monotonic() + 5.0
    mock_transport = MagicMock()
    gw._transport = mock_transport

    connector = threading.Timer(0.1, gw._set_connected, args=(True,))
    connector.start()
    try:
        msg = bytes([REPORT_LONG]) + bytes(19)
        gw.notify(WriteEvent(slot=1, pid=BOLT_PID, hid_message=msg))
    finally:
        connector.cancel()

    mock_transport.write.assert_called_once_with(msg)


# ── HidGateway.close ─────────────────────────────────────────────────────────


def test_close_closes_transport():
    event_listener = MagicMock(spec=EventListener)
    gw = HidGateway(_device_info(), event_listener)
    mock_transport = MagicMock()
    gw._transport = mock_transport

    gw.close()

    mock_transport.close.assert_called_once()


def test_close_noop_when_no_transport():
    event_listener = MagicMock(spec=EventListener)
    gw = HidGateway(_device_info(), event_listener)
    gw._transport = None
    gw.close()  # must not raise


def test_close_sets_stop_even_without_transport():
    """A gateway that never connected still has a running run() loop that must be told to exit."""
    event_listener = MagicMock(spec=EventListener)
    gw = HidGateway(_device_info(), event_listener)
    gw._transport = None

    gw.close()

    assert gw._stop.is_set()


# ── HidGateway.run teardown ─────────────────────────────────────────────────


def _stopping_gateway() -> HidGateway:
    """A connected gateway whose next read() fails the way close() makes it fail.

    Mirrors the shutdown sequence: the thread is blocked in read() when close() sets _stop and
    closes the transport, so the in-flight read raises with _stop already set.
    """
    gw = HidGateway(_device_info(), MagicMock(spec=EventListener))
    gw._transport = MagicMock()

    def read_after_close():
        gw._stop.set()
        raise TransportError("read on closed transport")

    gw._transport.read.side_effect = read_after_close
    gw._set_connected(True)
    return gw


def test_run_exits_without_reconnecting_when_stopped(mocker):
    """close() must actually stop the thread instead of having it reopen the closed transport."""
    gw = _stopping_gateway()
    try_connect = mocker.patch.object(gw, "_try_connect")

    gw.start()
    gw.join(timeout=2.0)

    assert not gw.is_alive(), "run() must exit once _stop is set"
    try_connect.assert_not_called()


def test_run_stopped_transport_error_does_not_mark_disconnected(mocker):
    """On shutdown the read failure is expected — it must not fan out a disconnect."""
    gw = _stopping_gateway()
    set_connected = mocker.patch.object(gw, "_set_connected")

    gw.run()

    set_connected.assert_not_called()


# ── HidGatewayBT._do_write ──────────────────────────────────────────────────


def test_bt_gateway_uses_write_output_report():
    event_listener = MagicMock(spec=EventListener)
    gw = HidGatewayBT(_bt_device_info(), event_listener)
    mock_transport = MagicMock()
    gw._transport = mock_transport
    gw._connected = True

    msg = bytes([REPORT_LONG]) + bytes(19)
    gw._do_write(mock_transport, msg)

    mock_transport.write_output_report.assert_called_once_with(msg)


# ── HidGatewayBT._set_connected ─────────────────────────────────────────────


def test_bt_gateway_set_connected_synthesizes_connection_event():
    event_listener = MagicMock(spec=EventListener)
    gw = HidGatewayBT(_bt_device_info(pid=0xB023), event_listener)

    gw._set_connected(True)

    event_listener.listen.assert_called_once()
    raw = event_listener.listen.call_args[0][0]
    assert raw[0] == 0x10  # REPORT_SHORT
    assert raw[1] == 0xFF  # slot
    assert raw[2] == 0x41  # Device Connection
    assert (raw[4] & 0x40) == 0  # connected (bit 6 clear)


def test_bt_gateway_set_connected_false_synthesizes_disconnection():
    event_listener = MagicMock(spec=EventListener)
    gw = HidGatewayBT(_bt_device_info(pid=0xB023), event_listener)

    gw._set_connected(False)

    raw = event_listener.listen.call_args[0][0]
    assert (raw[4] & 0x40) == 0x40  # disconnected (bit 6 set)


# ── HidGatewayBT regression: no TransportDisconnectedEvent ──────────────────


def test_bt_gateway_set_connected_false_does_not_publish_transport_disconnected():
    """Regression guard: TransportDisconnectedEvent must ONLY come from HidGatewayReceiver.

    HidGatewayBT handles both connect and disconnect via its own synthesized 0x41
    path (event_listener.listen). It must never publish TransportDisconnectedEvent
    to any topics channel because it doesn't own a Topics reference.
    """
    event_listener = MagicMock(spec=EventListener)
    gw = HidGatewayBT(_bt_device_info(pid=0xB023), event_listener)

    gw._set_connected(False)

    # BT gateway has no topics reference — the only side-effect is listen() being called.
    # Verify that the synthesized event is NOT a TransportDisconnectedEvent.
    raw = event_listener.listen.call_args[0][0]
    assert isinstance(raw, bytes), "BT gateway should only call event_listener.listen with raw bytes"
    assert not isinstance(raw, TransportDisconnectedEvent)


# ── Handle ownership: only the reader thread closes its transport (issue #108) ─


def test_close_from_foreign_thread_lets_reader_close_its_own_handle(make_fake_transport):
    """hid_close's CancelIo only cancels I/O issued by the calling thread.

    close() must therefore stop-and-join rather than close the handle itself.
    """
    transport = make_fake_transport()
    gw = HidGateway(_device_info(), MagicMock(spec=EventListener))
    gw._transport = transport
    gw._set_connected(True)
    gw.start()
    time.sleep(0.05)

    gw.close()

    assert not gw.is_alive()
    assert transport.close_count == 1
    assert transport.closed_by == gw.name, "the reader thread must be the one that closes"


def test_close_on_own_thread_does_not_deadlock(make_fake_transport, mocker):
    transport = make_fake_transport()
    gw = HidGateway(_device_info(), MagicMock(spec=EventListener))
    gw._transport = transport
    mocker.patch.object(gw, "_try_connect", side_effect=lambda: gw.close())

    gw.start()
    gw.join(timeout=2.0)

    assert not gw.is_alive()
    assert transport.close_count == 1


def test_close_still_closes_transport_when_thread_never_started(make_fake_transport):
    transport = make_fake_transport()
    gw = HidGateway(_device_info(), MagicMock(spec=EventListener))
    gw._transport = transport

    gw.close()

    assert transport.close_count == 1


# ── Thread-death guards ─────────────────────────────────────────────────────


def test_run_continues_after_none_read():
    """read() now polls, so None is the idle path — it must not reach hid_event.hex()."""
    event_listener = MagicMock(spec=EventListener)
    gw = HidGateway(_device_info(), event_listener)
    gw._transport = MagicMock()
    event = bytes([REPORT_LONG]) + bytes(19)

    def reads():
        yield None
        yield None
        yield event
        gw._stop.set()
        yield None

    gen = reads()
    gw._transport.read.side_effect = lambda: next(gen)
    gw._set_connected(True)

    gw.run()

    event_listener.listen.assert_called_once_with(event)


def test_try_connect_with_no_transport_and_changed_path_does_not_raise(mocker):
    info = _device_info()
    gw = HidGateway(info, MagicMock(spec=EventListener))
    gw._transport = None
    moved = HidDeviceInfo(
        path=b"/dev/hidraw9",
        vid=0x046D,
        pid=info.pid,
        usage_page=info.usage_page,
        usage=info.usage,
        connection_type="receiver",
    )
    mocker.patch("cleverswitch.gateway.hid_gateway.enumerate_hid_devices", return_value={info.pid: [moved]})
    transport_cls = mocker.patch("cleverswitch.gateway.hid_gateway.HIDTransport")

    gw._try_connect()  # must not raise AttributeError on the None transport

    assert gw._device_info.path == b"/dev/hidraw9"
    transport_cls.assert_called_once()
    assert gw._connected


def test_write_uses_snapshot_when_transport_is_nulled_concurrently(mocker):
    """_write must not re-read self._transport after its own None check."""
    gw = HidGateway(_device_info(), MagicMock(spec=EventListener))
    transport = MagicMock()
    gw._transport = transport
    gw._connected = True

    def null_it(_transport, _msg):
        gw._transport = None

    mocker.patch.object(gw, "_do_write", side_effect=null_it)

    gw._write(bytes([REPORT_LONG]) + bytes(19))  # must not raise AttributeError

    gw._do_write.assert_called_once()
    assert gw._do_write.call_args[0][0] is transport


# ── Reconnect backoff ───────────────────────────────────────────────────────


def test_backoff_grows_while_device_absent(mocker):
    gw = HidGateway(_device_info(), MagicMock(spec=EventListener))
    mocker.patch("cleverswitch.gateway.hid_gateway.enumerate_hid_devices", return_value={})
    waits: list[float] = []
    mocker.patch.object(gw._stop, "wait", side_effect=lambda t: waits.append(t))

    for _ in range(3):
        gw._try_connect()

    assert waits == [1.0, 2.0, 4.0]


def test_backoff_is_capped(mocker):
    gw = HidGateway(_device_info(), MagicMock(spec=EventListener))
    mocker.patch("cleverswitch.gateway.hid_gateway.enumerate_hid_devices", return_value={})
    waits: list[float] = []
    mocker.patch.object(gw._stop, "wait", side_effect=lambda t: waits.append(t))

    for _ in range(20):
        gw._try_connect()

    assert max(waits) == _RECONNECT_BACKOFF_MAX


def test_backoff_resets_after_successful_connect(mocker):
    info = _device_info()
    gw = HidGateway(info, MagicMock(spec=EventListener))
    gw._backoff = 16.0
    same_path = HidDeviceInfo(
        path=info.path,
        vid=0x046D,
        pid=info.pid,
        usage_page=info.usage_page,
        usage=info.usage,
        connection_type="receiver",
    )
    mocker.patch("cleverswitch.gateway.hid_gateway.enumerate_hid_devices", return_value={info.pid: [same_path]})
    mocker.patch("cleverswitch.gateway.hid_gateway.HIDTransport")

    gw._try_connect()

    assert gw._backoff == _RECONNECT_BACKOFF_MIN
