"""Unit tests for subscriber/set_report_flag_subscriber.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from cleverswitch.event.set_report_flag_event import SetReportFlagEvent
from cleverswitch.event.write_event import WriteEvent
from cleverswitch.hidpp.constants import (
    BOLT_PID,
    FEATURE_CHANGE_HOST,
    FEATURE_REPROG_CONTROLS_V4,
    HOST_SWITCH_CIDS,
    KEY_FLAG_ANALYTICS,
    KEY_FLAG_DIVERTABLE,
    KEY_FLAG_PERSISTENTLY_DIVERTABLE,
)
from cleverswitch.model.logi_device import LogiDevice
from cleverswitch.registry.logi_device_registry import LogiDeviceRegistry
from cleverswitch.subscriber.set_report_flag_subscriber import SetReportFlagSubscriber
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics

PID = BOLT_PID
WPID = 0x407B
REPROG_IDX = 8


def _make_topics():
    return Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        flags=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
    )


def _make_device(reprog_idx=REPROG_IDX, supported_flags=None):
    features = {FEATURE_CHANGE_HOST: 9}
    if reprog_idx is not None:
        features[FEATURE_REPROG_CONTROLS_V4] = reprog_idx
    device = LogiDevice(
        wpid=WPID, pid=PID, slot=1, role="keyboard",
        available_features=features,
    )
    if supported_flags is not None:
        device.supported_flags = set(supported_flags)
    return device


def test_analytics_flag_sends_analytics_params_for_all_es_cids():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = SetReportFlagSubscriber(registry, topics)

    device = _make_device(supported_flags={KEY_FLAG_ANALYTICS})
    registry.register(WPID, device)

    event = SetReportFlagEvent(slot=1, pid=PID, wpid=WPID)
    sub.notify(event)

    # One write per HOST_SWITCH_CID (3 total)
    assert topics.write.publish.call_count == len(HOST_SWITCH_CIDS)
    for call in topics.write.publish.call_args_list:
        assert isinstance(call[0][0], WriteEvent)


def test_divertable_flag_sends_divert_bfield():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = SetReportFlagSubscriber(registry, topics)

    device = _make_device(supported_flags={KEY_FLAG_DIVERTABLE})
    registry.register(WPID, device)

    event = SetReportFlagEvent(slot=1, pid=PID, wpid=WPID)
    sub.notify(event)

    assert topics.write.publish.call_count == len(HOST_SWITCH_CIDS)
    for call in topics.write.publish.call_args_list:
        assert isinstance(call[0][0], WriteEvent)


def test_divertable_and_persistently_divertable_includes_persist_flags():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = SetReportFlagSubscriber(registry, topics)

    device = _make_device(supported_flags={KEY_FLAG_DIVERTABLE, KEY_FLAG_PERSISTENTLY_DIVERTABLE})
    registry.register(WPID, device)

    event = SetReportFlagEvent(slot=1, pid=PID, wpid=WPID)
    sub.notify(event)

    assert topics.write.publish.call_count == len(HOST_SWITCH_CIDS)


def test_enable_false_sends_clear_divert_bfield():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = SetReportFlagSubscriber(registry, topics)

    device = _make_device(supported_flags={KEY_FLAG_DIVERTABLE})
    registry.register(WPID, device)

    event = SetReportFlagEvent(slot=1, pid=PID, wpid=WPID, enable=False)
    sub.notify(event)

    assert topics.write.publish.call_count == len(HOST_SWITCH_CIDS)


def test_unknown_device_no_write():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = SetReportFlagSubscriber(registry, topics)

    event = SetReportFlagEvent(slot=1, pid=PID, wpid=0x9999)
    sub.notify(event)

    topics.write.publish.assert_not_called()


def test_no_reprog_controls_v4_feature_no_write():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = SetReportFlagSubscriber(registry, topics)

    device = _make_device(reprog_idx=None, supported_flags={KEY_FLAG_DIVERTABLE})
    registry.register(WPID, device)

    event = SetReportFlagEvent(slot=1, pid=PID, wpid=WPID)
    sub.notify(event)

    topics.write.publish.assert_not_called()


def test_empty_supported_flags_no_write():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = SetReportFlagSubscriber(registry, topics)

    device = _make_device(supported_flags=set())
    registry.register(WPID, device)

    event = SetReportFlagEvent(slot=1, pid=PID, wpid=WPID)
    sub.notify(event)

    topics.write.publish.assert_not_called()


def test_non_set_report_flag_event_is_noop():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = SetReportFlagSubscriber(registry, topics)
    sub.notify("not an event")  # must not raise

    topics.write.publish.assert_not_called()
