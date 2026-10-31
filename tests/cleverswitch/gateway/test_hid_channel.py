"""Unit tests for gateway/hid_channel.py."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

from cleverswitch.errors.errors import TransportError
from cleverswitch.gateway.hid_channel import _OPEN_RETRY_DELAYS, HidChannel
from cleverswitch.hidpp.constants import BOLT_PID, CONNECTION_BLUETOOTH, CONNECTION_RECEIVER, REPORT_LONG
from cleverswitch.hidpp.transport import HidDeviceInfo
from cleverswitch.listener.event_listener import EventListener


def _device_info(pid=BOLT_PID, connection_type=CONNECTION_RECEIVER):
    return HidDeviceInfo(
        path=b"/dev/hidraw0", vid=0x046D, pid=pid, usage_page=0xFF00, usage=0x0002, connection_type=connection_type
    )


def _bt_device_info(pid=0xB023):
    return HidDeviceInfo(
        path=b"/dev/hidraw1", vid=0x046D, pid=pid, usage_page=0xFF43, usage=0x0202, connection_type=CONNECTION_BLUETOOTH
    )


# ── HidChannel.submit ────────────────────────────────────────────────────────


def test_submit_drops_write_when_disconnected_and_was_previously_connected():
    event_listener = MagicMock(spec=EventListener)
    gw = HidChannel(_device_info(), event_listener, MagicMock())
    gw._connected = False
    gw._ever_connected = True
    mock_transport = MagicMock()
    gw._transport = mock_transport

    gw.submit(b"\x11" + bytes(19))

    mock_transport.write.assert_not_called()


def test_submit_writes_when_connected():
    event_listener = MagicMock(spec=EventListener)
    gw = HidChannel(_device_info(), event_listener, MagicMock())
    gw._connected = True
    gw._ever_connected = True
    mock_transport = MagicMock()
    gw._transport = mock_transport

    msg = bytes([REPORT_LONG]) + bytes(19)
    gw.submit(msg)

    mock_transport.write.assert_called_once_with(msg)


def test_submit_drops_write_when_never_connected_and_grace_expired():
    """Regression guard for #92: a collection that never connects must not park the drain thread.

    HidChannel.submit runs on the owning DeviceLink's write-topic drain thread. The old code spun
    `while not self._connected` forever when _ever_connected was False, so the queue behind it grew
    without bound. The wait is now capped by a one-shot grace window measured from construction.
    """
    event_listener = MagicMock(spec=EventListener)
    gw = HidChannel(_device_info(), event_listener, MagicMock())
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


def test_submit_within_grace_writes_once_hid_channel_connects():
    event_listener = MagicMock(spec=EventListener)
    gw = HidChannel(_device_info(), event_listener, MagicMock())
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
    assert HidChannel(info, MagicMock(spec=EventListener), MagicMock()).device_info is info


# ── HidChannel.close ─────────────────────────────────────────────────────────


def test_close_closes_transport():
    event_listener = MagicMock(spec=EventListener)
    gw = HidChannel(_device_info(), event_listener, MagicMock())
    mock_transport = MagicMock()
    gw._transport = mock_transport

    gw.close()

    mock_transport.close.assert_called_once()


def test_close_noop_when_no_transport():
    event_listener = MagicMock(spec=EventListener)
    gw = HidChannel(_device_info(), event_listener, MagicMock())
    gw._transport = None
    gw.close()  # must not raise


def test_close_sets_stop_even_without_transport():
    """A channel that never connected still has a running run() loop that must be told to exit."""
    event_listener = MagicMock(spec=EventListener)
    gw = HidChannel(_device_info(), event_listener, MagicMock())
    gw._transport = None

    gw.close()

    assert gw._stop.is_set()


# ── HidChannel.run teardown ─────────────────────────────────────────────────


def _stopping_channel() -> HidChannel:
    """A connected channel whose next read() fails the way close() makes it fail.

    Mirrors the shutdown sequence: the thread is blocked in read() when close() sets _stop and
    closes the transport, so the in-flight read raises with _stop already set.
    """
    gw = HidChannel(_device_info(), MagicMock(spec=EventListener), MagicMock())
    gw._transport = MagicMock()

    def read_after_close():
        gw._stop.set()
        raise TransportError("read on closed transport")

    gw._transport.read.side_effect = read_after_close
    gw._set_connected(True)
    return gw


def test_run_exits_without_reconnecting_when_stopped(mocker):
    """close() must actually stop the thread instead of having it reopen the closed transport."""
    gw = _stopping_channel()
    try_open = mocker.patch.object(gw, "_try_open")

    gw.start()
    gw.join(timeout=2.0)

    assert not gw.is_alive(), "run() must exit once _stop is set"
    try_open.assert_not_called()


def test_run_stopped_transport_error_does_not_mark_disconnected(mocker):
    """On shutdown the read failure is expected — it must not fan out a disconnect."""
    gw = _stopping_channel()
    set_connected = mocker.patch.object(gw, "_set_connected")

    gw.run()

    set_connected.assert_not_called()


# ── Write mode ──────────────────────────────────────────────────────────────


def test_default_write_uses_write():
    transport = MagicMock()
    gw = _connected_channel(HidChannel(_device_info(), MagicMock(spec=EventListener), MagicMock()), transport)

    msg = bytes([REPORT_LONG]) + bytes(19)
    gw._write(msg)

    transport.write.assert_called_once_with(msg)
    transport.write_output_report.assert_not_called()


def test_output_report_mode_uses_write_output_report():
    transport = MagicMock()
    gw = HidChannel(_bt_device_info(), MagicMock(spec=EventListener), MagicMock())
    _connected_channel(gw, transport)

    msg = bytes([REPORT_LONG]) + bytes(19)
    gw._write(msg)

    transport.write_output_report.assert_called_once_with(msg)
    transport.write.assert_not_called()


# ── State reporting ─────────────────────────────────────────────────────────


def test_set_connected_reports_change_after_updating_state():
    seen = []
    gw = HidChannel(_device_info(), MagicMock(spec=EventListener), lambda: seen.append(gw.connected))

    gw._set_connected(True)
    gw._set_connected(False)

    assert seen == [True, False]


def test_set_connected_never_emits_events_itself():
    event_listener = MagicMock(spec=EventListener)
    gw = HidChannel(_device_info(), event_listener, MagicMock())

    gw._set_connected(True)
    gw._set_connected(False)

    event_listener.emit.assert_not_called()
    event_listener.listen.assert_not_called()


# ── Handle ownership: only the reader thread closes its transport (issue #108) ─


def test_close_from_foreign_thread_lets_reader_close_its_own_handle(make_fake_transport):
    """hid_close's CancelIo only cancels I/O issued by the calling thread.

    close() must therefore stop-and-join rather than close the handle itself.
    """
    transport = make_fake_transport()
    gw = HidChannel(_device_info(), MagicMock(spec=EventListener), MagicMock())
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
    gw = HidChannel(_device_info(), MagicMock(spec=EventListener), MagicMock())
    gw._transport = transport
    gw.attach(b"/dev/hidraw0")
    mocker.patch.object(gw, "_try_open", side_effect=lambda *_: gw.close())

    gw.start()
    gw.join(timeout=2.0)

    assert not gw.is_alive()
    assert transport.close_count == 1


def test_close_still_closes_transport_when_thread_never_started(make_fake_transport):
    transport = make_fake_transport()
    gw = HidChannel(_device_info(), MagicMock(spec=EventListener), MagicMock())
    gw._transport = transport

    gw.close()

    assert transport.close_count == 1


# ── Thread-death guards ─────────────────────────────────────────────────────


def test_run_continues_after_none_read():
    """read() now polls, so None is the idle path — it must not reach hid_event.hex()."""
    event_listener = MagicMock(spec=EventListener)
    gw = HidChannel(_device_info(), event_listener, MagicMock())
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


def test_write_uses_snapshot_when_transport_is_nulled_concurrently():
    """_write must not re-read self._transport after its own None check."""
    gw = HidChannel(_device_info(), MagicMock(spec=EventListener), MagicMock())
    transport = MagicMock()
    gw._transport = transport
    gw._connected = True

    def null_it(_msg):
        gw._transport = None

    transport.write.side_effect = null_it

    gw._write(bytes([REPORT_LONG]) + bytes(19))  # must not raise AttributeError

    transport.write.assert_called_once()


# ── Write failure is handed to the reader thread ────────────────────────────


def _connected_channel(gw, transport):
    gw._transport = transport
    gw._connected = True
    gw._ever_connected = True
    return gw


def test_write_failure_leaves_state_to_the_reader(fake_transport):
    gw = _connected_channel(HidChannel(_device_info(), MagicMock(spec=EventListener), MagicMock()), fake_transport)
    fake_transport.fail_next = TransportError("write failed")

    gw._write(bytes([REPORT_LONG]) + bytes(19))

    assert gw._connected
    assert gw._reopen_requested.is_set()


def test_writes_dropped_while_reconnect_is_pending(fake_transport):
    gw = _connected_channel(HidChannel(_device_info(), MagicMock(spec=EventListener), MagicMock()), fake_transport)
    gw._reopen_requested.set()

    gw.submit(bytes([REPORT_LONG]) + bytes(19))

    assert fake_transport.written == []


def _stop_after_reopen(gw, transport, mocker, error=None):
    def reopen():
        gw._stop.set()
        if error is not None:
            raise error

    return mocker.patch.object(transport, "try_reopen", side_effect=reopen)


def test_reader_reopens_quietly_after_write_failure(fake_transport, mocker):
    on_state_changed = MagicMock()
    gw = _connected_channel(HidChannel(_device_info(), MagicMock(spec=EventListener), on_state_changed), fake_transport)
    fake_transport.fail_next = TransportError("write failed")
    gw._write(bytes([REPORT_LONG]) + bytes(19))
    reopen = _stop_after_reopen(gw, fake_transport, mocker)

    gw.run()

    reopen.assert_called_once_with()
    on_state_changed.assert_not_called()
    assert gw.connected
    assert not gw._reopen_requested.is_set()


def test_reader_reports_disconnect_when_reopen_after_write_failure_fails(fake_transport, mocker):
    on_state_changed = MagicMock()
    gw = _connected_channel(HidChannel(_device_info(), MagicMock(spec=EventListener), on_state_changed), fake_transport)
    gw._reopen_requested.set()
    _stop_after_reopen(gw, fake_transport, mocker, error=OSError("gone"))

    gw.run()

    on_state_changed.assert_called_once_with()
    assert not gw.connected
    assert not gw._reopen_requested.is_set()


def test_writes_resume_after_quiet_reopen(fake_transport, mocker):
    gw = _connected_channel(HidChannel(_device_info(), MagicMock(spec=EventListener), MagicMock()), fake_transport)
    gw._reopen_requested.set()
    _stop_after_reopen(gw, fake_transport, mocker)
    gw.run()
    msg = bytes([REPORT_LONG]) + bytes(19)

    gw.submit(msg)

    assert fake_transport.written == [msg]


def test_reconnect_clears_pending_reopen():
    gw = HidChannel(_device_info(), MagicMock(spec=EventListener), MagicMock())
    gw._reopen_requested.set()

    gw._set_connected(True)

    assert not gw._reopen_requested.is_set()


# ── Attach / detach ─────────────────────────────────────────────────────────

PATH = b"/dev/hidraw0"
OTHER_PATH = b"/dev/hidraw7"


def _commanded_channel(mocker, transports=None, open_error=None):
    on_state_changed = MagicMock()
    gw = HidChannel(_device_info(), MagicMock(spec=EventListener), on_state_changed)
    transport_cls = mocker.patch("cleverswitch.gateway.hid_channel.HIDTransport")
    if open_error is not None:
        transport_cls.side_effect = open_error
    elif transports is not None:
        transport_cls.side_effect = transports
    sleeps: list[float | None] = []
    mocker.patch.object(gw, "_sleep", side_effect=sleeps.append)
    return gw, transport_cls, on_state_changed, sleeps


def test_without_attach_the_reader_sleeps_until_a_command(mocker):
    gw, transport_cls, _, sleeps = _commanded_channel(mocker)

    gw._step()

    transport_cls.assert_not_called()
    assert sleeps == [None]


def test_attach_opens_the_path_and_reports_connected(mocker):
    gw, transport_cls, on_state_changed, _ = _commanded_channel(mocker)

    gw.attach(PATH)
    gw._step()

    transport_cls.assert_called_once_with(CONNECTION_RECEIVER, PATH)
    assert gw.connected
    on_state_changed.assert_called_once_with()


def test_detach_closes_the_handle_and_reports_disconnected(mocker, make_fake_transport):
    transport = make_fake_transport()
    gw, _, on_state_changed, _ = _commanded_channel(mocker, transports=[transport])
    gw.attach(PATH)
    gw._step()

    gw.detach()
    gw._step()

    assert transport.close_count == 1
    assert not gw.connected
    assert on_state_changed.call_count == 2


def test_attach_with_a_new_path_reopens_on_it(mocker, make_fake_transport):
    first, second = make_fake_transport(), make_fake_transport()
    gw, transport_cls, _, _ = _commanded_channel(mocker, transports=[first, second])
    gw.attach(PATH)
    gw._step()

    gw.attach(OTHER_PATH)
    gw._step()
    gw._step()

    assert [c.args[1] for c in transport_cls.call_args_list] == [PATH, OTHER_PATH]
    assert first.close_count == 1
    assert gw.connected


def test_read_failure_waits_for_the_next_attach(mocker, make_fake_transport):
    transport = make_fake_transport()
    gw, transport_cls, _, sleeps = _commanded_channel(mocker, transports=[transport, make_fake_transport()])
    gw.attach(PATH)
    gw._step()
    transport.fail_next = TransportError("gone")

    gw._step()
    gw._step()

    assert not gw.connected
    assert transport_cls.call_count == 1
    assert sleeps == [None]

    gw.attach(PATH)
    gw._step()

    assert transport_cls.call_count == 2
    assert gw.connected


def test_read_failure_after_a_newer_attach_reopens_at_once(mocker, make_fake_transport):
    """Windows keeps one path across a quick drop and return: the attach for the return arrives while
    the stale handle is still open, and the read failure that follows must not be taken as final."""
    transport = make_fake_transport()
    gw, transport_cls, _, sleeps = _commanded_channel(mocker, transports=[transport, make_fake_transport()])
    gw.attach(PATH)
    gw._step()
    gw.attach(PATH)
    transport.fail_next = TransportError("stale handle")

    gw._step()
    gw._step()

    assert transport_cls.call_count == 2
    assert gw.connected
    assert sleeps == []


def test_open_failure_retries_with_growing_delays_then_waits(mocker, caplog):
    gw, transport_cls, on_state_changed, sleeps = _commanded_channel(mocker, open_error=OSError("busy"))
    gw.attach(PATH)

    for _ in range(len(_OPEN_RETRY_DELAYS) + 2):
        gw._step()

    assert transport_cls.call_count == len(_OPEN_RETRY_DELAYS) + 1
    assert sleeps == [*_OPEN_RETRY_DELAYS, None]
    assert any("Cannot open HID device pid=0xC548" in r.message for r in caplog.records)
    on_state_changed.assert_not_called()


def test_first_retry_waits_despite_the_wake_left_by_attach(mocker):
    gw, _, _, _ = _commanded_channel(mocker, open_error=OSError("not permitted"))
    wake_at_sleep = []
    gw._sleep.side_effect = lambda _timeout: wake_at_sleep.append(gw._wake.is_set())
    gw.attach(PATH)

    gw._step()

    assert wake_at_sleep == [False]


def test_new_attach_after_giving_up_tries_again_with_a_fresh_budget(mocker):
    gw, transport_cls, _, sleeps = _commanded_channel(mocker, open_error=OSError("busy"))
    gw.attach(PATH)
    for _ in range(len(_OPEN_RETRY_DELAYS) + 1):
        gw._step()
    sleeps.clear()

    gw.attach(PATH)
    gw._step()

    assert transport_cls.call_count == len(_OPEN_RETRY_DELAYS) + 2
    assert sleeps == [_OPEN_RETRY_DELAYS[0]]


def test_open_failure_warning_mentions_input_monitoring_on_macos(mocker, caplog):
    mocker.patch("cleverswitch.gateway.hid_channel.get_system", return_value="Darwin")
    gw, _, _, _ = _commanded_channel(mocker, open_error=OSError("not permitted"))
    gw.attach(PATH)

    for _ in range(len(_OPEN_RETRY_DELAYS) + 1):
        gw._step()

    assert any("Input Monitoring" in r.message for r in caplog.records)


def test_attach_wakes_a_sleeping_reader(mocker, make_fake_transport):
    transport_cls = mocker.patch("cleverswitch.gateway.hid_channel.HIDTransport", return_value=make_fake_transport())
    gw = HidChannel(_device_info(), MagicMock(spec=EventListener), MagicMock())
    gw.start()
    try:
        gw.attach(PATH)
        assert gw._connected_signal.wait(2.0)
    finally:
        gw.close()

    transport_cls.assert_called_once_with(CONNECTION_RECEIVER, PATH)
    assert not gw.is_alive()


def test_sleep_returns_on_wake_and_clears_it():
    gw = HidChannel(_device_info(), MagicMock(spec=EventListener), MagicMock())
    gw._wake.set()

    gw._sleep(5.0)

    assert not gw._wake.is_set()
