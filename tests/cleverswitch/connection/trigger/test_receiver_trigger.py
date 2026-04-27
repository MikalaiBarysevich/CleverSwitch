"""Unit tests for connection/trigger/receiver_trigger.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.cleverswitch.connection.trigger.receiver_trigger import (
    ENABLE_HIDPP_NOTIFICATIONS_MESSAGE,
    ENUMERATE_CONNECTED_DEVICES_MESSAGE,
    ReceiverConnectionTrigger,
)
from src.cleverswitch.event.write_event import WriteEvent
from src.cleverswitch.hidpp.constants import BOLT_PID
from src.cleverswitch.hidpp.transport import HidDeviceInfo
from src.cleverswitch.topic.topic import Topic
from src.cleverswitch.topic.topics import Topics


def _device_info():
    return HidDeviceInfo(
        path=b"/dev/hidraw0", vid=0x046D, pid=BOLT_PID, usage_page=0xFF00, usage=0x0002, connection_type="receiver"
    )


def _make_topics():
    return Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        flags=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
    )


def test_trigger_publishes_enable_then_enumerate_messages():
    topics = _make_topics()
    trigger = ReceiverConnectionTrigger(_device_info(), topics)
    trigger.trigger()

    assert topics.write.publish.call_count == 2

    first_event = topics.write.publish.call_args_list[0][0][0]
    assert isinstance(first_event, WriteEvent)
    assert first_event.hid_message == ENABLE_HIDPP_NOTIFICATIONS_MESSAGE
    assert first_event.pid == BOLT_PID

    second_event = topics.write.publish.call_args_list[1][0][0]
    assert isinstance(second_event, WriteEvent)
    assert second_event.hid_message == ENUMERATE_CONNECTED_DEVICES_MESSAGE
    assert second_event.pid == BOLT_PID


def test_enumerate_message_format():
    assert len(ENUMERATE_CONNECTED_DEVICES_MESSAGE) == 7
    assert ENUMERATE_CONNECTED_DEVICES_MESSAGE[0] == 0x10  # REPORT_SHORT
    assert ENUMERATE_CONNECTED_DEVICES_MESSAGE[1] == 0xFF  # receiver


def test_enable_message_format():
    assert ENABLE_HIDPP_NOTIFICATIONS_MESSAGE == bytes([0x10, 0xFF, 0x80, 0x00, 0x00, 0x09, 0x00])
    assert len(ENABLE_HIDPP_NOTIFICATIONS_MESSAGE) == 7
