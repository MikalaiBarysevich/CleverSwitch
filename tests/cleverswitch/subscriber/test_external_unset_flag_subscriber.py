"""Unit tests for subscriber/external_unset_flag_subscriber.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from cleverswitch.event.external_unset_flag_event import ExternalUnsetFlagEvent
from cleverswitch.event.set_report_flag_event import SetReportFlagEvent
from cleverswitch.hidpp.constants import BOLT_PID, FEATURE_CHANGE_HOST, FEATURE_REPROG_CONTROLS_V4
from cleverswitch.model.logi_device import LogiDevice
from cleverswitch.registry.logi_device_registry import LogiDeviceRegistry
from cleverswitch.subscriber.external_unset_flag_subscriber import ExternalUnsetFlagSubscriber
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics

PID = BOLT_PID
REPROG_IDX = 8


def _make_topics():
    return Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        flags=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
    )


def _make_device(slot=1, reprog_idx=REPROG_IDX):
    features = {FEATURE_CHANGE_HOST: 9}
    if reprog_idx is not None:
        features[FEATURE_REPROG_CONTROLS_V4] = reprog_idx
    return LogiDevice(
        wpid=0x407B, pid=PID, slot=slot, role="keyboard",
        available_features=features,
    )


def test_known_device_correct_feature_index_publishes_set_report_flag_event():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = ExternalUnsetFlagSubscriber(registry, topics)

    device = _make_device()
    registry.register(0x407B, device)

    event = ExternalUnsetFlagEvent(slot=1, pid=PID, feature_index=REPROG_IDX, cid=0x00D1)
    sub.notify(event)

    topics.flags.publish.assert_called_once()
    published = topics.flags.publish.call_args[0][0]
    assert isinstance(published, SetReportFlagEvent)
    assert published.cids == {0x00D1}


def test_unknown_device_wrong_slot_no_publish():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = ExternalUnsetFlagSubscriber(registry, topics)

    event = ExternalUnsetFlagEvent(slot=5, pid=PID, feature_index=REPROG_IDX, cid=0x00D1)
    sub.notify(event)

    topics.flags.publish.assert_not_called()


def test_wrong_feature_index_no_publish():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = ExternalUnsetFlagSubscriber(registry, topics)

    device = _make_device()
    registry.register(0x407B, device)

    event = ExternalUnsetFlagEvent(slot=1, pid=PID, feature_index=99, cid=0x00D1)
    sub.notify(event)

    topics.flags.publish.assert_not_called()


def test_non_external_unset_flag_event_is_noop():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = ExternalUnsetFlagSubscriber(registry, topics)
    sub.notify("not an event")  # must not raise

    topics.flags.publish.assert_not_called()
