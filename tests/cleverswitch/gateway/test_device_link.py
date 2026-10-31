"""Unit tests for gateway/device_link.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from cleverswitch.event.link_channel_changed_event import CHANNEL_GATT, LinkChannelChangedEvent
from cleverswitch.event.transport_connected_event import TransportConnectedEvent
from cleverswitch.event.transport_disconnected_event import TransportDisconnectedEvent
from cleverswitch.event.write_event import WriteEvent
from cleverswitch.gateway.device_link import DeviceLink
from cleverswitch.gateway.gatt_channel import GattChannel
from cleverswitch.gateway.hid_channel import HidChannel
from cleverswitch.gateway.write_router import WriteRouter
from cleverswitch.hidpp.constants import BOLT_PID, CONNECTION_BLUETOOTH, CONNECTION_RECEIVER, REPORT_LONG
from cleverswitch.hidpp.transport import HidDeviceInfo
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


def _hid_channel(connected=False):
    hid_channel = MagicMock(spec=HidChannel)
    hid_channel.connected = connected
    return hid_channel


def _collection(usage, path=None):
    return HidDeviceInfo(
        path=path or f"/dev/hidraw{usage}".encode(),
        vid=0x046D,
        pid=BOLT_PID,
        usage_page=0xFF00,
        usage=usage,
        connection_type=CONNECTION_RECEIVER,
    )


def _factory(hid_channels):
    pending = list(hid_channels)
    return MagicMock(side_effect=lambda _info: pending.pop(0))


def _make_link(hid_channels=None, router=None, gatt=None, pid=BOLT_PID, connection_type=CONNECTION_RECEIVER):
    topics = _make_topics()
    listener = MagicMock(spec=EventListener)
    hid_channels = hid_channels if hid_channels is not None else [_hid_channel()]
    link = DeviceLink(pid, connection_type, topics, listener, router or WriteRouter())
    link.attach(_factory(hid_channels), gatt)
    link.update([_collection(i + 1) for i in range(len(hid_channels))])
    return link, topics, listener, hid_channels


def _emitted(listener):
    return [c.args[0] for c in listener.emit.call_args_list]


# ── Writes ───────────────────────────────────────────────────────────────────


def test_subscribes_to_write_topic():
    link, topics, _, _ = _make_link()
    topics.write.subscribe.assert_called_once_with(link)


def test_routes_write_to_selected_hid_channel():
    first, second = _hid_channel(), _hid_channel()
    router = MagicMock(spec=WriteRouter)
    router.select.return_value = second
    link, _, _, _ = _make_link([first, second], router)

    link.notify(WriteEvent(slot=1, pid=BOLT_PID, hid_message=MSG))

    router.select.assert_called_once_with(MSG, [first, second])
    second.submit.assert_called_once_with(MSG)
    first.submit.assert_not_called()


def test_ignores_writes_for_other_pids():
    link, _, _, hid_channels = _make_link()
    link.notify(WriteEvent(slot=1, pid=0x9999, hid_message=MSG))
    hid_channels[0].submit.assert_not_called()


def test_ignores_non_write_events():
    link, _, _, hid_channels = _make_link()
    link.notify("not a WriteEvent")
    hid_channels[0].submit.assert_not_called()


def test_drops_write_when_router_selects_nothing():
    router = MagicMock(spec=WriteRouter)
    router.select.return_value = None
    link, _, _, hid_channels = _make_link(router=router)

    link.notify(WriteEvent(slot=1, pid=BOLT_PID, hid_message=MSG))

    hid_channels[0].submit.assert_not_called()


def test_write_goes_over_gatt_when_it_accepts():
    gatt = MagicMock(spec=GattChannel)
    gatt.write.return_value = True
    link, _, _, hid_channels = _make_link(gatt=gatt, pid=BT_PID, connection_type=CONNECTION_BLUETOOTH)

    link.notify(WriteEvent(slot=0xFF, pid=BT_PID, hid_message=MSG))

    gatt.write.assert_called_once_with(MSG)
    hid_channels[0].submit.assert_not_called()


def test_write_falls_back_to_hid_when_gatt_declines():
    gatt = MagicMock(spec=GattChannel)
    gatt.write.return_value = False
    link, _, _, hid_channels = _make_link(gatt=gatt, pid=BT_PID, connection_type=CONNECTION_BLUETOOTH)

    link.notify(WriteEvent(slot=0xFF, pid=BT_PID, hid_message=MSG))

    hid_channels[0].submit.assert_called_once_with(MSG)


# ── Presence ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("connection_type", [CONNECTION_RECEIVER, CONNECTION_BLUETOOTH])
def test_emits_connected_when_the_only_collection_opens(connection_type):
    hid_channel = _hid_channel()
    link, _, listener, _ = _make_link([hid_channel], connection_type=connection_type)

    hid_channel.connected = True
    link.on_hid_state_changed()

    assert _emitted(listener) == [TransportConnectedEvent(slot=0, pid=BOLT_PID, connection_type=connection_type)]


def test_emits_disconnected_when_the_collection_closes():
    hid_channel = _hid_channel()
    link, _, listener, _ = _make_link([hid_channel])
    hid_channel.connected = True
    link.on_hid_state_changed()
    listener.emit.reset_mock()

    hid_channel.connected = False
    link.on_hid_state_changed()

    assert _emitted(listener) == [TransportDisconnectedEvent(slot=0, pid=BOLT_PID)]


def test_reconnect_emits_connected_again():
    hid_channel = _hid_channel()
    link, _, listener, _ = _make_link([hid_channel])

    for state in (True, False, True):
        hid_channel.connected = state
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
    short, long = _hid_channel(), _hid_channel()
    link, _, listener, _ = _make_link([short, long])

    long.connected = True
    link.on_hid_state_changed()
    listener.emit.assert_not_called()

    short.connected = True
    link.on_hid_state_changed()
    assert _emitted(listener) == [TransportConnectedEvent(slot=0, pid=BOLT_PID, connection_type=CONNECTION_RECEIVER)]


def test_multi_collection_device_connects_and_disconnects_once():
    short, long = _hid_channel(), _hid_channel()
    link, _, listener, _ = _make_link([short, long])

    for hid_channel in (short, long):
        hid_channel.connected = True
        link.on_hid_state_changed()
    for hid_channel in (short, long):
        hid_channel.connected = False
        link.on_hid_state_changed()

    assert [type(e) for e in _emitted(listener)] == [TransportConnectedEvent, TransportDisconnectedEvent]


def test_repeated_reports_without_change_emit_nothing():
    hid_channel = _hid_channel(connected=True)
    link, _, listener, _ = _make_link([hid_channel])
    link.on_hid_state_changed()
    listener.emit.reset_mock()

    link.on_hid_state_changed()

    listener.emit.assert_not_called()


# ── GATT follows presence ────────────────────────────────────────────────────


def test_presence_activates_and_deactivates_gatt():
    hid_channel = _hid_channel()
    gatt = MagicMock(spec=GattChannel)
    link, _, _, _ = _make_link([hid_channel], gatt=gatt)

    hid_channel.connected = True
    link.on_hid_state_changed()
    gatt.activate.assert_called_once()

    hid_channel.connected = False
    link.on_hid_state_changed()
    gatt.deactivate.assert_called_once()


@pytest.mark.parametrize("up", [True, False])
def test_gatt_state_is_published_as_channel_change(up):
    link, _, listener, _ = _make_link(pid=BT_PID, connection_type=CONNECTION_BLUETOOTH)

    link.on_gatt_state(up)

    assert _emitted(listener) == [LinkChannelChangedEvent(slot=0, pid=BT_PID, channel=CHANNEL_GATT, up=up)]


def test_gatt_drop_leaves_the_device_present():
    hid_channel = _hid_channel()
    link, _, listener, _ = _make_link([hid_channel], gatt=MagicMock(spec=GattChannel))
    hid_channel.connected = True
    link.on_hid_state_changed()
    listener.emit.reset_mock()

    link.on_gatt_state(False)

    assert not any(isinstance(e, TransportDisconnectedEvent) for e in _emitted(listener))


# ── Lifecycle ────────────────────────────────────────────────────────────────


def test_start_starts_gatt_hid_channel_and_listener():
    gatt = MagicMock(spec=GattChannel)
    link, _, listener, hid_channels = _make_link([_hid_channel(), _hid_channel()], gatt=gatt)

    link.start()

    gatt.start.assert_called_once()
    for hid_channel in hid_channels:
        hid_channel.start.assert_called_once()
    listener.start.assert_called_once()


def test_close_closes_gatt_and_every_hid_channel():
    gatt = MagicMock(spec=GattChannel)
    link, _, _, hid_channels = _make_link([_hid_channel(), _hid_channel()], gatt=gatt)

    link.close()

    gatt.close.assert_called_once()
    for hid_channel in hid_channels:
        hid_channel.close.assert_called_once()


def test_start_and_close_without_gatt():
    link, _, listener, hid_channels = _make_link()
    link.start()
    link.close()
    hid_channels[0].start.assert_called_once()
    hid_channels[0].close.assert_called_once()


# ── update ───────────────────────────────────────────────────────────────────


def _bare_link(hid_channels):
    link = DeviceLink(BOLT_PID, CONNECTION_RECEIVER, _make_topics(), MagicMock(spec=EventListener), WriteRouter())
    factory = _factory(hid_channels)
    link.attach(factory)
    return link, factory


def test_update_attaches_each_listed_collection_to_its_path():
    short, long = _hid_channel(), _hid_channel()
    link, _ = _bare_link([short, long])

    link.update([_collection(1, b"/a"), _collection(2, b"/b")])

    short.attach.assert_called_once_with(b"/a")
    long.attach.assert_called_once_with(b"/b")


def test_update_creates_a_channel_once_per_collection():
    hid_channel = _hid_channel()
    link, factory = _bare_link([hid_channel])

    link.update([_collection(2, b"/a")])
    link.update([_collection(2, b"/b")])

    factory.assert_called_once()
    assert [c.args[0] for c in hid_channel.attach.call_args_list] == [b"/a", b"/b"]


def test_update_detaches_collections_no_longer_listed():
    short, long = _hid_channel(), _hid_channel()
    link, _ = _bare_link([short, long])
    link.update([_collection(1), _collection(2)])

    link.update([_collection(2)])

    short.detach.assert_called_once_with()
    long.detach.assert_not_called()


def test_update_with_nothing_listed_parks_every_channel():
    short, long = _hid_channel(), _hid_channel()
    link, _ = _bare_link([short, long])
    link.update([_collection(1), _collection(2)])

    link.update([])

    short.detach.assert_called_once_with()
    long.detach.assert_called_once_with()


def test_channel_added_before_start_is_started_by_start():
    hid_channel = _hid_channel()
    link, _ = _bare_link([hid_channel])
    link.update([_collection(2)])
    hid_channel.start.assert_not_called()

    link.start()

    hid_channel.start.assert_called_once_with()


def test_channel_added_after_start_is_started_at_once():
    first, late = _hid_channel(), _hid_channel()
    link, _ = _bare_link([first, late])
    link.update([_collection(1)])
    link.start()

    link.update([_collection(1), _collection(2)])

    late.start.assert_called_once_with()
    first.start.assert_called_once_with()


def test_late_collection_is_offered_to_the_write_router():
    first, late = _hid_channel(connected=True), _hid_channel()
    router = MagicMock(spec=WriteRouter)
    router.select.return_value = None
    link, _ = _bare_link([first, late])
    link._router = router
    link.update([_collection(1)])

    link.update([_collection(1), _collection(2)])
    link.notify(WriteEvent(slot=1, pid=BOLT_PID, hid_message=MSG))

    router.select.assert_called_once_with(MSG, [first, late])
