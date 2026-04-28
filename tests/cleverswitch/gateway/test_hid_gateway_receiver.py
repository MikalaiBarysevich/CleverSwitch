"""Unit tests for gateway/hid_gateway_receiver.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from cleverswitch.event.transport_disconnected_event import TransportDisconnectedEvent
from cleverswitch.gateway.hid_gateway_receiver import HidGatewayReceiver
from cleverswitch.hidpp.constants import BOLT_PID
from cleverswitch.hidpp.transport import HidDeviceInfo
from cleverswitch.listener.event_listener import EventListener
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics


def _device_info(pid: int = BOLT_PID) -> HidDeviceInfo:
    return HidDeviceInfo(
        path=b"/dev/hidraw0", vid=0x046D, pid=pid, usage_page=0xFF00, usage=0x0002, connection_type="receiver"
    )


def _make_topics() -> Topics:
    return Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        flags=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
    )


def _make_gateway(pid: int = BOLT_PID) -> tuple[HidGatewayReceiver, MagicMock, Topics]:
    event_listener = MagicMock(spec=EventListener)
    topics = _make_topics()
    trigger = MagicMock()
    gw = HidGatewayReceiver(_device_info(pid), event_listener, topics, trigger)
    return gw, trigger, topics


# ── _set_connected(True) ─────────────────────────────────────────────────────


def test_set_connected_true_calls_trigger():
    gw, trigger, topics = _make_gateway()
    gw._set_connected(True)
    trigger.trigger.assert_called_once()


def test_set_connected_true_does_not_publish_transport_disconnected():
    gw, trigger, topics = _make_gateway()
    gw._set_connected(True)
    topics.hid_event.publish.assert_not_called()


def test_set_connected_true_updates_connected_flag():
    gw, trigger, topics = _make_gateway()
    gw._set_connected(True)
    assert gw._connected is True
    assert gw._ever_connected is True


# ── _set_connected(False) ────────────────────────────────────────────────────


def test_set_connected_false_publishes_transport_disconnected_event():
    gw, trigger, topics = _make_gateway(pid=BOLT_PID)
    gw._set_connected(False)

    topics.hid_event.publish.assert_called_once()
    event = topics.hid_event.publish.call_args[0][0]
    assert isinstance(event, TransportDisconnectedEvent)
    assert event.pid == BOLT_PID


def test_set_connected_false_does_not_call_trigger():
    gw, trigger, topics = _make_gateway()
    gw._set_connected(False)
    trigger.trigger.assert_not_called()


def test_set_connected_false_updates_connected_flag():
    gw, trigger, topics = _make_gateway()
    gw._connected = True
    gw._set_connected(False)
    assert gw._connected is False


def test_set_connected_false_publishes_with_slot_zero():
    gw, trigger, topics = _make_gateway()
    gw._set_connected(False)
    event = topics.hid_event.publish.call_args[0][0]
    assert event.slot == 0


# ── Reconnect after disconnect ───────────────────────────────────────────────


def test_reconnect_after_disconnect_calls_trigger_again():
    gw, trigger, topics = _make_gateway()

    gw._set_connected(True)
    gw._set_connected(False)
    gw._set_connected(True)

    assert trigger.trigger.call_count == 2
