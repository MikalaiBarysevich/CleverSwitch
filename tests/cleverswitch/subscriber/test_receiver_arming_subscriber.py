"""Unit tests for subscriber/receiver_arming_subscriber.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from cleverswitch.event.transport_connected_event import TransportConnectedEvent
from cleverswitch.event.transport_disconnected_event import TransportDisconnectedEvent
from cleverswitch.event.write_event import WriteEvent
from cleverswitch.hidpp.constants import BOLT_PID, CONNECTION_BLUETOOTH, CONNECTION_RECEIVER
from cleverswitch.subscriber.receiver_arming_subscriber import (
    ENABLE_HIDPP_NOTIFICATIONS_MESSAGE,
    ENUMERATE_CONNECTED_DEVICES_MESSAGE,
    ReceiverArmingSubscriber,
)
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics


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
    subscriber = ReceiverArmingSubscriber(topics)
    topics.hid_event.subscribe.assert_called_once_with(subscriber)


def test_receiver_connect_publishes_enable_then_enumerate():
    topics = _make_topics()
    ReceiverArmingSubscriber(topics).notify(
        TransportConnectedEvent(slot=0, pid=BOLT_PID, connection_type=CONNECTION_RECEIVER)
    )

    assert [c.args[0] for c in topics.write.publish.call_args_list] == [
        WriteEvent(slot=-1, pid=BOLT_PID, hid_message=ENABLE_HIDPP_NOTIFICATIONS_MESSAGE),
        WriteEvent(slot=-1, pid=BOLT_PID, hid_message=ENUMERATE_CONNECTED_DEVICES_MESSAGE),
    ]


def test_bluetooth_connect_is_ignored():
    topics = _make_topics()
    ReceiverArmingSubscriber(topics).notify(
        TransportConnectedEvent(slot=0, pid=0xB023, connection_type=CONNECTION_BLUETOOTH)
    )
    topics.write.publish.assert_not_called()


def test_other_events_are_ignored():
    topics = _make_topics()
    ReceiverArmingSubscriber(topics).notify(TransportDisconnectedEvent(slot=0, pid=BOLT_PID))
    topics.write.publish.assert_not_called()


def test_enumerate_message_format():
    assert ENUMERATE_CONNECTED_DEVICES_MESSAGE == bytes([0x10, 0xFF, 0x80, 0x02, 0x02, 0x00, 0x00])


def test_enable_message_format():
    assert ENABLE_HIDPP_NOTIFICATIONS_MESSAGE == bytes([0x10, 0xFF, 0x80, 0x00, 0x00, 0x09, 0x00])
