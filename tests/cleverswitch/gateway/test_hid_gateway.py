"""Unit tests for gateway/hid_gateway.py and gateway/hid_gateway_bt.py."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

from cleverswitch.errors.errors import TransportError
from cleverswitch.event.transport_connected_event import TransportConnectedEvent
from cleverswitch.event.transport_disconnected_event import TransportDisconnectedEvent
from cleverswitch.gateway.hid_gateway import (
    _RECONNECT_BACKOFF_MAX,
    _RECONNECT_BACKOFF_MIN,
    _RECONNECT_INTERVAL,
    HidGateway,
)
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


# ── HidGateway.submit ────────────────────────────────────────────────────────


def test_submit_drops_write_when_disconnected_and_was_previously_connected():
    event_listener = MagicMock(spec=EventListener)
    gw = HidGateway(_device_info(), event_listener)
    gw._connected = False
    gw._ever_connected = True
    mock_transport = MagicMock()
    gw._transport = mock_transport

    gw.submit(b"\x11" + bytes(19))

    mock_transport.write.assert_not_called()


def test_submit_writes_when_connected():
    event_listener = MagicMock(spec=EventListener)
    gw = HidGateway(_device_info(), event_listener)
    gw._connected = True
    gw._ever_connected = True
    mock_transport = MagicMock()
    gw._transport = mock_transport

    msg = bytes([REPORT_LONG]) + bytes(19)
    gw.submit(msg)

    mock_transport.write.assert_called_once_with(msg)


def test_submit_drops_write_when_never_connected_and_grace_expired():
    """Regression guard for #92: a collection that never connects must not park the drain thread.

    HidGateway.submit runs on the owning DeviceLink's write-topic drain thread. The old code spun
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

    # Run on a worker so a reintroduced spin fails the test instead of hanging the suite.
    worker = threading.Thread(target=gw.submit, args=(b"\x11" + bytes(19),), daemon=True)
    worker.start()
    worker.join(timeout=2.0)

    assert not worker.is_alive(), "submit must return once the first-connect grace has expired"
    mock_transport.write.assert_not_called()


def test_submit_within_grace_writes_once_gateway_connects():
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
        gw.submit(msg)
    finally:
        connector.cancel()

    mock_transport.write.assert_called_once_with(msg)


def test_device_info_is_exposed():
    info = _device_info()
    assert HidGateway(info, MagicMock(spec=EventListener)).device_info is info


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


def test_bt_gateway_set_connected_emits_transport_connected():
    event_listener = MagicMock(spec=EventListener)
    gw = HidGatewayBT(_bt_device_info(pid=0xB023), event_listener)

    gw._set_connected(True)

    event_listener.emit.assert_called_once_with(
        TransportConnectedEvent(slot=0, pid=0xB023, connection_type="bluetooth")
    )
    event_listener.listen.assert_not_called()


def test_bt_gateway_set_connected_false_emits_transport_disconnected():
    event_listener = MagicMock(spec=EventListener)
    gw = HidGatewayBT(_bt_device_info(pid=0xB023), event_listener)

    gw._set_connected(False)

    event_listener.emit.assert_called_once_with(TransportDisconnectedEvent(slot=0, pid=0xB023))
    event_listener.listen.assert_not_called()


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


# ── Write failure is handed to the reader thread ────────────────────────────


def _connected_gateway(gw, transport):
    gw._transport = transport
    gw._connected = True
    gw._ever_connected = True
    return gw


def test_write_failure_leaves_state_to_the_reader(fake_transport):
    gw = _connected_gateway(HidGateway(_device_info(), MagicMock(spec=EventListener)), fake_transport)
    fake_transport.fail_next = TransportError("write failed")

    gw._write(bytes([REPORT_LONG]) + bytes(19))

    assert gw._connected
    assert gw._reopen_requested.is_set()


def test_writes_dropped_while_reconnect_is_pending(fake_transport):
    gw = _connected_gateway(HidGateway(_device_info(), MagicMock(spec=EventListener)), fake_transport)
    gw._reopen_requested.set()

    gw.submit(bytes([REPORT_LONG]) + bytes(19))

    assert fake_transport.written == []


def _run_one_iteration(gw, mocker):
    def stop_after(state):
        type(gw)._set_connected(gw, state)
        gw._stop.set()

    return mocker.patch.object(gw, "_set_connected", side_effect=stop_after)


def test_reader_marks_disconnected_after_write_failure(fake_transport, mocker):
    gw = _connected_gateway(HidGateway(_device_info(), MagicMock(spec=EventListener)), fake_transport)
    gw._reopen_requested.set()
    set_connected = _run_one_iteration(gw, mocker)

    gw.run()

    set_connected.assert_called_once_with(False)
    assert not gw._connected
    assert not gw._reopen_requested.is_set()


def test_bt_write_failure_emits_disconnect_from_reader(fake_transport, mocker):
    event_listener = MagicMock(spec=EventListener)
    gw = _connected_gateway(HidGatewayBT(_bt_device_info(), event_listener), fake_transport)
    fake_transport.fail_next = TransportError("write failed")
    gw._write(bytes([REPORT_LONG]) + bytes(19))
    event_listener.emit.assert_not_called()

    _run_one_iteration(gw, mocker)
    gw.run()

    event_listener.emit.assert_called_once_with(TransportDisconnectedEvent(slot=0, pid=0xB023))


def test_reconnect_clears_pending_reopen():
    gw = HidGateway(_device_info(), MagicMock(spec=EventListener))
    gw._reopen_requested.set()

    gw._set_connected(True)

    assert not gw._reopen_requested.is_set()


# ── Reconnect backoff ───────────────────────────────────────────────────────


def _present(info):
    return {
        info.pid: [
            HidDeviceInfo(
                path=info.path,
                vid=0x046D,
                pid=info.pid,
                usage_page=info.usage_page,
                usage=info.usage,
                connection_type="receiver",
            )
        ]
    }


def test_absent_device_is_polled_at_a_flat_interval(mocker):
    """A device away on another host must be noticed promptly when it returns (issue #121)."""
    gw = HidGateway(_device_info(), MagicMock(spec=EventListener))
    mocker.patch("cleverswitch.gateway.hid_gateway.enumerate_hid_devices", return_value={})
    waits: list[float] = []
    mocker.patch.object(gw._stop, "wait", side_effect=lambda t: waits.append(t))

    for _ in range(20):
        gw._try_connect()

    assert waits == [_RECONNECT_INTERVAL] * 20


def test_absence_resets_open_failure_backoff(mocker):
    gw = HidGateway(_device_info(), MagicMock(spec=EventListener))
    gw._backoff = 16.0
    mocker.patch("cleverswitch.gateway.hid_gateway.enumerate_hid_devices", return_value={})
    mocker.patch.object(gw._stop, "wait")

    gw._try_connect()

    assert gw._backoff == _RECONNECT_BACKOFF_MIN


def test_backoff_grows_while_device_fails_to_open(mocker):
    info = _device_info()
    gw = HidGateway(info, MagicMock(spec=EventListener))
    mocker.patch("cleverswitch.gateway.hid_gateway.enumerate_hid_devices", return_value=_present(info))
    mocker.patch("cleverswitch.gateway.hid_gateway.HIDTransport", side_effect=OSError("open failed"))
    waits: list[float] = []
    mocker.patch.object(gw._stop, "wait", side_effect=lambda t: waits.append(t))

    for _ in range(3):
        gw._try_connect()

    assert waits == [1.0, 2.0, 4.0]


def test_open_failure_backoff_is_capped(mocker):
    info = _device_info()
    gw = HidGateway(info, MagicMock(spec=EventListener))
    mocker.patch("cleverswitch.gateway.hid_gateway.enumerate_hid_devices", return_value=_present(info))
    mocker.patch("cleverswitch.gateway.hid_gateway.HIDTransport", side_effect=OSError("open failed"))
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
