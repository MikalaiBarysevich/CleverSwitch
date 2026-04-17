"""Unit tests for connection/trigger/receiver_trigger.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.cleverswitch.connection.trigger.receiver_trigger import ENUMERATE_CONNECTED_DEVICES_MESSAGE, ReceiverConnectionTrigger
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


def test_trigger_publishes_enumerate_message():
    topics = _make_topics()
    trigger = ReceiverConnectionTrigger(_device_info(), topics)
    trigger.trigger()

    topics.write.publish.assert_called_once()
    event = topics.write.publish.call_args[0][0]
    assert isinstance(event, WriteEvent)
    assert event.hid_message == ENUMERATE_CONNECTED_DEVICES_MESSAGE
    assert event.pid == BOLT_PID


def test_enumerate_message_format():
    assert len(ENUMERATE_CONNECTED_DEVICES_MESSAGE) == 7
    assert ENUMERATE_CONNECTED_DEVICES_MESSAGE[0] == 0x10  # REPORT_SHORT
    assert ENUMERATE_CONNECTED_DEVICES_MESSAGE[1] == 0xFF  # receiver
