"""Unit tests for gateway/device_link.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from cleverswitch.event.link_channel_changed_event import LinkChannelChangedEvent
from cleverswitch.event.transport_connected_event import TransportConnectedEvent
from cleverswitch.event.transport_disconnected_event import TransportDisconnectedEvent
from cleverswitch.event.write_event import WriteEvent
from cleverswitch.gateway.device_link import DeviceLink
from cleverswitch.gateway.gatt_channel import GattChannel
from cleverswitch.gateway.hid_gateway import HidGateway
from cleverswitch.gateway.write_router import WriteRouter
from cleverswitch.hidpp.constants import BOLT_PID, REPORT_LONG
from cleverswitch.listener.event_listener import EventListener
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics

MSG = bytes([REPORT_LONG]) + bytes(19)
BT_PID = 0xB023


def _make_topics():
    return Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        flags=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
    )


def _gateway(connected=False):
    gateway = MagicMock(spec=HidGateway)
    gateway.connected = connected
    return gateway


def _make_link(gateways=None, router=None, gatt=None, pid=BOLT_PID, connection_type="receiver"):
    topics = _make_topics()
    listener = MagicMock(spec=EventListener)
    gateways = gateways if gateways is not None else [_gateway()]
    link = DeviceLink(pid, connection_type, topics, listener, router or WriteRouter())
    link.attach(gateways, gatt)
    return link, topics, listener, gateways


def _emitted(listener):
    return [c.args[0] for c in listener.emit.call_args_list]


# ── Writes ───────────────────────────────────────────────────────────────────


def test_subscribes_to_write_topic():
    link, topics, _, _ = _make_link()
    topics.write.subscribe.assert_called_once_with(link)


def test_routes_write_to_selected_gateway():
    first, second = _gateway(), _gateway()
    router = MagicMock(spec=WriteRouter)
    router.select.return_value = second
    link, _, _, _ = _make_link([first, second], router)

    link.notify(WriteEvent(slot=1, pid=BOLT_PID, hid_message=MSG))

    router.select.assert_called_once_with(MSG, [first, second])
    second.submit.assert_called_once_with(MSG)
    first.submit.assert_not_called()


def test_ignores_writes_for_other_pids():
    link, _, _, gateways = _make_link()
    link.notify(WriteEvent(slot=1, pid=0x9999, hid_message=MSG))
    gateways[0].submit.assert_not_called()


def test_ignores_non_write_events():
    link, _, _, gateways = _make_link()
    link.notify("not a WriteEvent")
    gateways[0].submit.assert_not_called()


def test_drops_write_when_router_selects_nothing():
    router = MagicMock(spec=WriteRouter)
    router.select.return_value = None
    link, _, _, gateways = _make_link(router=router)

    link.notify(WriteEvent(slot=1, pid=BOLT_PID, hid_message=MSG))

    gateways[0].submit.assert_not_called()


def test_write_goes_over_gatt_when_it_accepts():
    gatt = MagicMock(spec=GattChannel)
    gatt.write.return_value = True
    link, _, _, gateways = _make_link(gatt=gatt, pid=BT_PID, connection_type="bluetooth")

    link.notify(WriteEvent(slot=0xFF, pid=BT_PID, hid_message=MSG))

    gatt.write.assert_called_once_with(MSG)
    gateways[0].submit.assert_not_called()


def test_write_falls_back_to_hid_when_gatt_declines():
    gatt = MagicMock(spec=GattChannel)
    gatt.write.return_value = False
    link, _, _, gateways = _make_link(gatt=gatt, pid=BT_PID, connection_type="bluetooth")

    link.notify(WriteEvent(slot=0xFF, pid=BT_PID, hid_message=MSG))

    gateways[0].submit.assert_called_once_with(MSG)


# ── Presence ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("connection_type", ["receiver", "bluetooth"])
def test_emits_connected_when_the_only_collection_opens(connection_type):
    gateway = _gateway()
    link, _, listener, _ = _make_link([gateway], connection_type=connection_type)

    gateway.connected = True
    link.on_hid_state_changed()

    assert _emitted(listener) == [TransportConnectedEvent(slot=0, pid=BOLT_PID, connection_type=connection_type)]


def test_emits_disconnected_when_the_collection_closes():
    gateway = _gateway()
    link, _, listener, _ = _make_link([gateway])
    gateway.connected = True
    link.on_hid_state_changed()
    listener.emit.reset_mock()

    gateway.connected = False
    link.on_hid_state_changed()

    assert _emitted(listener) == [TransportDisconnectedEvent(slot=0, pid=BOLT_PID)]


def test_reconnect_emits_connected_again():
    gateway = _gateway()
    link, _, listener, _ = _make_link([gateway])

    for state in (True, False, True):
        gateway.connected = state
        link.on_hid_state_changed()

    assert [type(e) for e in _emitted(listener)] == [
        TransportConnectedEvent,
        TransportDisconnectedEvent,
        TransportConnectedEvent,
    ]


def test_never_present_link_emits_nothing_on_close():
    link, _, listener, _ = _make_link()
    link.on_hid_state_changed()
    listener.emit.assert_not_called()


def test_multi_collection_device_is_present_only_when_every_collection_is_open():
    """Windows splits HID++ short and long reports into two collections. Arming writes go to the
    short one, so announcing the device while it is still closed would drop them."""
    short, long = _gateway(), _gateway()
    link, _, listener, _ = _make_link([short, long])

    long.connected = True
    link.on_hid_state_changed()
    listener.emit.assert_not_called()

    short.connected = True
    link.on_hid_state_changed()
    assert _emitted(listener) == [TransportConnectedEvent(slot=0, pid=BOLT_PID, connection_type="receiver")]


def test_multi_collection_device_connects_and_disconnects_once():
    short, long = _gateway(), _gateway()
    link, _, listener, _ = _make_link([short, long])

    for gateway in (short, long):
        gateway.connected = True
        link.on_hid_state_changed()
    for gateway in (short, long):
        gateway.connected = False
        link.on_hid_state_changed()

    assert [type(e) for e in _emitted(listener)] == [TransportConnectedEvent, TransportDisconnectedEvent]


def test_repeated_reports_without_change_emit_nothing():
    gateway = _gateway(connected=True)
    link, _, listener, _ = _make_link([gateway])
    link.on_hid_state_changed()
    listener.emit.reset_mock()

    link.on_hid_state_changed()

    listener.emit.assert_not_called()


# ── GATT follows presence ────────────────────────────────────────────────────


def test_presence_activates_and_deactivates_gatt():
    gateway = _gateway()
    gatt = MagicMock(spec=GattChannel)
    link, _, _, _ = _make_link([gateway], gatt=gatt)

    gateway.connected = True
    link.on_hid_state_changed()
    gatt.activate.assert_called_once()

    gateway.connected = False
    link.on_hid_state_changed()
    gatt.deactivate.assert_called_once()


@pytest.mark.parametrize("up", [True, False])
def test_gatt_state_is_published_as_channel_change(up):
    link, _, listener, _ = _make_link(pid=BT_PID, connection_type="bluetooth")

    link.on_gatt_state(up)

    assert _emitted(listener) == [LinkChannelChangedEvent(slot=0, pid=BT_PID, channel="gatt", up=up)]


def test_gatt_drop_leaves_the_device_present():
    gateway = _gateway()
    link, _, listener, _ = _make_link([gateway], gatt=MagicMock(spec=GattChannel))
    gateway.connected = True
    link.on_hid_state_changed()
    listener.emit.reset_mock()

    link.on_gatt_state(False)

    assert not any(isinstance(e, TransportDisconnectedEvent) for e in _emitted(listener))


# ── Lifecycle ────────────────────────────────────────────────────────────────


def test_start_starts_gatt_gateways_and_listener():
    gatt = MagicMock(spec=GattChannel)
    link, _, listener, gateways = _make_link([_gateway(), _gateway()], gatt=gatt)

    link.start()

    gatt.start.assert_called_once()
    for gateway in gateways:
        gateway.start.assert_called_once()
    listener.start.assert_called_once()


def test_close_closes_gatt_and_every_gateway():
    gatt = MagicMock(spec=GattChannel)
    link, _, _, gateways = _make_link([_gateway(), _gateway()], gatt=gatt)

    link.close()

    gatt.close.assert_called_once()
    for gateway in gateways:
        gateway.close.assert_called_once()


def test_start_and_close_without_gatt():
    link, _, listener, gateways = _make_link()
    link.start()
    link.close()
    gateways[0].start.assert_called_once()
    gateways[0].close.assert_called_once()
