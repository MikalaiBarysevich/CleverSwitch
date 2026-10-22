"""Unit tests for subscriber/direct_device_connection_subscriber.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from cleverswitch.event.device_connected_event import DeviceConnectedEvent
from cleverswitch.event.transport_connected_event import TransportConnectedEvent
from cleverswitch.event.transport_disconnected_event import TransportDisconnectedEvent
from cleverswitch.hidpp.constants import BOLT_PID
from cleverswitch.parser.parser import parse
from cleverswitch.subscriber.direct_device_connection_subscriber import DirectDeviceConnectionSubscriber
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics

BT_PID = 0xB023


def _make_topics():
    return Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        flags=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
    )


def test_subscribes_to_hid_event():
    topics = _make_topics()
    subscriber = DirectDeviceConnectionSubscriber(topics)
    topics.hid_event.subscribe.assert_called_once_with(subscriber)


def test_bluetooth_connect_publishes_device_connected():
    topics = _make_topics()
    DirectDeviceConnectionSubscriber(topics).notify(
        TransportConnectedEvent(slot=0, pid=BT_PID, connection_type="bluetooth")
    )

    topics.hid_event.publish.assert_called_once_with(
        DeviceConnectedEvent(slot=0xFF, pid=BT_PID, wpid=BT_PID, link_established=True, device_type=None)
    )


def test_matches_the_event_the_forged_0x41_used_to_produce():
    """Downstream subscribers must see exactly what the old synthesized connection report parsed to."""
    topics = _make_topics()
    forged = bytes([0x10, 0xFF, 0x41, 0x00, 0x00, BT_PID & 0xFF, BT_PID >> 8])

    DirectDeviceConnectionSubscriber(topics).notify(
        TransportConnectedEvent(slot=0, pid=BT_PID, connection_type="bluetooth")
    )

    assert topics.hid_event.publish.call_args.args[0] == parse(BT_PID, forged)


def test_receiver_connect_is_ignored():
    topics = _make_topics()
    DirectDeviceConnectionSubscriber(topics).notify(
        TransportConnectedEvent(slot=0, pid=BOLT_PID, connection_type="receiver")
    )
    topics.hid_event.publish.assert_not_called()


def test_other_events_are_ignored():
    topics = _make_topics()
    DirectDeviceConnectionSubscriber(topics).notify(TransportDisconnectedEvent(slot=0, pid=BT_PID))
    topics.hid_event.publish.assert_not_called()
