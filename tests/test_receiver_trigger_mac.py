"""Tests for ReceiverConnectionTriggerMac — 0xB5 pairing info queries."""

from unittest.mock import MagicMock

from cleverswitch.connection.trigger.receiver_trigger_mac import ReceiverConnectionTriggerMac
from cleverswitch.event.write_event import WriteEvent
from cleverswitch.hidpp.constants import BOLT_PID, DEVICE_RECEIVER, GET_LONG_REGISTER_RSP, REGISTER_PAIRING_INFO, REPORT_SHORT
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics


def _make_trigger() -> tuple[ReceiverConnectionTriggerMac, MagicMock]:
    device_info = MagicMock()
    device_info.pid = BOLT_PID
    write_topic = MagicMock()
    topics = Topics(
        hid_event=MagicMock(spec=Topic),
        write=write_topic,
        device_info=MagicMock(spec=Topic),
        divert=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
    )
    trigger = ReceiverConnectionTriggerMac(device_info, topics)
    return trigger, write_topic


class TestReceiverConnectionTriggerMac:

    def test_trigger_publishes_six_write_events(self):
        trigger, write_topic = _make_trigger()
        trigger.trigger()
        assert write_topic.publish.call_count == 6

    def test_trigger_messages_are_short_reports(self):
        trigger, write_topic = _make_trigger()
        trigger.trigger()
        for call in write_topic.publish.call_args_list:
            event = call[0][0]
            assert isinstance(event, WriteEvent)
            assert len(event.hid_message) == 7
            assert event.hid_message[0] == REPORT_SHORT

    def test_trigger_messages_target_receiver(self):
        trigger, write_topic = _make_trigger()
        trigger.trigger()
        for call in write_topic.publish.call_args_list:
            event = call[0][0]
            assert event.hid_message[1] == DEVICE_RECEIVER

    def test_trigger_messages_use_get_long_register(self):
        trigger, write_topic = _make_trigger()
        trigger.trigger()
        for call in write_topic.publish.call_args_list:
            event = call[0][0]
            assert event.hid_message[2] == GET_LONG_REGISTER_RSP
            assert event.hid_message[3] == REGISTER_PAIRING_INFO

    def test_trigger_sub_pages_cover_slots_1_to_6(self):
        trigger, write_topic = _make_trigger()
        trigger.trigger()
        sub_pages = [call[0][0].hid_message[4] for call in write_topic.publish.call_args_list]
        assert sub_pages == [0x20, 0x21, 0x22, 0x23, 0x24, 0x25]

    def test_trigger_write_events_have_correct_pid(self):
        trigger, write_topic = _make_trigger()
        trigger.trigger()
        for call in write_topic.publish.call_args_list:
            event = call[0][0]
            assert event.pid == BOLT_PID
            assert event.slot == -1
