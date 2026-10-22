"""Unit tests for gateway/hid_gateway_receiver.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from cleverswitch.errors.errors import TransportError
from cleverswitch.event.transport_connected_event import TransportConnectedEvent
from cleverswitch.event.transport_disconnected_event import TransportDisconnectedEvent
from cleverswitch.gateway.hid_gateway_receiver import HidGatewayReceiver
from cleverswitch.hidpp.constants import BOLT_PID
from cleverswitch.hidpp.transport import HidDeviceInfo
from cleverswitch.listener.event_listener import EventListener


def _device_info(pid: int = BOLT_PID) -> HidDeviceInfo:
    return HidDeviceInfo(
        path=b"/dev/hidraw0", vid=0x046D, pid=pid, usage_page=0xFF00, usage=0x0002, connection_type="receiver"
    )


def _make_gateway(pid: int = BOLT_PID) -> tuple[HidGatewayReceiver, MagicMock]:
    event_listener = MagicMock(spec=EventListener)
    return HidGatewayReceiver(_device_info(pid), event_listener), event_listener


def _emitted(listener: MagicMock) -> list:
    return [c.args[0] for c in listener.emit.call_args_list]


# ── _set_connected(True) ─────────────────────────────────────────────────────


def test_set_connected_true_emits_transport_connected():
    gw, listener = _make_gateway()
    gw._set_connected(True)
    assert _emitted(listener) == [TransportConnectedEvent(slot=0, pid=BOLT_PID, connection_type="receiver")]
    listener.listen.assert_not_called()


def test_set_connected_true_updates_connected_flag():
    gw, _ = _make_gateway()
    gw._set_connected(True)
    assert gw._connected is True
    assert gw._ever_connected is True


# ── _set_connected(False) ────────────────────────────────────────────────────


def test_set_connected_false_emits_transport_disconnected():
    gw, listener = _make_gateway()
    gw._set_connected(False)
    assert _emitted(listener) == [TransportDisconnectedEvent(slot=0, pid=BOLT_PID)]


def test_set_connected_false_updates_connected_flag():
    gw, _ = _make_gateway()
    gw._connected = True
    gw._set_connected(False)
    assert gw._connected is False


# ── Shutdown ─────────────────────────────────────────────────────────────────


def test_stopped_read_failure_emits_no_transport_disconnected():
    """close() closing the transport makes the in-flight read fail — that is not a real disconnect."""
    gw, listener = _make_gateway()
    gw._transport = MagicMock()

    def read_after_close():
        gw._stop.set()
        raise TransportError("read on closed transport")

    gw._transport.read.side_effect = read_after_close
    gw._set_connected(True)
    listener.emit.reset_mock()

    gw.run()

    listener.emit.assert_not_called()


# ── Reconnect after disconnect ───────────────────────────────────────────────


def test_reconnect_after_disconnect_emits_connected_again():
    gw, listener = _make_gateway()

    gw._set_connected(True)
    gw._set_connected(False)
    gw._set_connected(True)

    assert [type(e) for e in _emitted(listener)] == [
        TransportConnectedEvent,
        TransportDisconnectedEvent,
        TransportConnectedEvent,
    ]


# ── Write failure ────────────────────────────────────────────────────────────


def test_write_failure_emits_transport_disconnected_from_reader(fake_transport, mocker):
    gw, listener = _make_gateway()
    gw._transport = fake_transport
    gw._set_connected(True)
    listener.emit.reset_mock()
    fake_transport.fail_next = TransportError("write failed")

    gw._write(bytes([0x11]) + bytes(19))
    listener.emit.assert_not_called()

    def stop_after(state):
        type(gw)._set_connected(gw, state)
        gw._stop.set()

    mocker.patch.object(gw, "_set_connected", side_effect=stop_after)
    gw.run()

    assert _emitted(listener) == [TransportDisconnectedEvent(slot=0, pid=BOLT_PID)]
