"""Unit tests for listener/event_listener.py."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

from cleverswitch.event.hidpp_notification_event import HidppNotificationEvent
from cleverswitch.hidpp.constants import BOLT_PID, REPORT_LONG
from cleverswitch.hidpp.transport import HidDeviceInfo
from cleverswitch.listener.event_listener import EventListener
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics


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


def test_listen_queues_raw_event():
    topics = _make_topics()
    listener = EventListener(_device_info(), topics)
    listener.daemon = True
    listener.start()

    # Build a valid notification (fn=0, sw_id=0)
    raw = bytes([REPORT_LONG, 0x01, 0x05, 0x00]) + bytes(16)
    listener.listen(raw)
    time.sleep(0.1)

    topics.hid_event.publish.assert_called_once()
    event = topics.hid_event.publish.call_args[0][0]
    assert isinstance(event, HidppNotificationEvent)


def test_listen_skips_unparseable_events():
    topics = _make_topics()
    listener = EventListener(_device_info(), topics)
    listener.daemon = True
    listener.start()

    # Unknown short report
    raw = bytes([0x10, 0x01, 0x42, 0x00, 0x00, 0x00, 0x00])
    listener.listen(raw)
    time.sleep(0.1)

    topics.hid_event.publish.assert_not_called()


def test_connection_trigger_called_on_start():
    topics = _make_topics()
    trigger = MagicMock()
    listener = EventListener(_device_info(), topics, connection_trigger=trigger)
    listener.daemon = True
    listener.start()
    time.sleep(0.1)

    trigger.trigger.assert_called_once()


def test_no_connection_trigger_runs_fine():
    topics = _make_topics()
    listener = EventListener(_device_info(), topics, connection_trigger=None)
    listener.daemon = True
    listener.start()

    raw = bytes([REPORT_LONG, 0x01, 0x05, 0x00]) + bytes(16)
    listener.listen(raw)
    time.sleep(0.1)

    topics.hid_event.publish.assert_called_once()
