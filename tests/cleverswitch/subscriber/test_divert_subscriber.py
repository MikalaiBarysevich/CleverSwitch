"""Unit tests for subscriber/divert_subscriber.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from cleverswitch.event.divert_event import DivertEvent
from cleverswitch.event.write_event import WriteEvent
from cleverswitch.hidpp.constants import BOLT_PID, FEATURE_CHANGE_HOST, FEATURE_REPROG_CONTROLS_V4
from cleverswitch.model.logi_device import LogiDevice
from cleverswitch.registry.logi_device_registry import LogiDeviceRegistry
from cleverswitch.subscriber.divert_subscriber import DivertSubscriber
from cleverswitch.topic.topic import Topic

PID = BOLT_PID
WPID = 0x407B
REPROG_IDX = 8


def _make_topics():
    return {
        "event_topic": MagicMock(spec=Topic),
        "write_topic": MagicMock(spec=Topic),
        "device_info_topic": MagicMock(spec=Topic),
        "divert_topic": MagicMock(spec=Topic),
    }


def _make_device(reprog_idx=REPROG_IDX, persistently_divertable=None):
    features = {FEATURE_CHANGE_HOST: 9}
    if reprog_idx is not None:
        features[FEATURE_REPROG_CONTROLS_V4] = reprog_idx
    return LogiDevice(
        wpid=WPID, pid=PID, slot=1, role="keyboard",
        available_features=features,
        persistently_divertable_cids=persistently_divertable or set(),
    )


def test_divert_publishes_write_event_per_cid():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DivertSubscriber(registry, topics)

    device = _make_device()
    registry.register(WPID, device)

    event = DivertEvent(slot=1, pid=PID, wpid=WPID, cids={0x00D1, 0x00D2})
    sub.notify(event)

    assert topics["write_topic"].publish.call_count == 2
    for call in topics["write_topic"].publish.call_args_list:
        assert isinstance(call[0][0], WriteEvent)


def test_divert_ignores_unknown_device():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DivertSubscriber(registry, topics)

    event = DivertEvent(slot=1, pid=PID, wpid=0x9999, cids={0x00D1})
    sub.notify(event)

    topics["write_topic"].publish.assert_not_called()


def test_divert_ignores_device_without_reprog():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DivertSubscriber(registry, topics)

    device = _make_device(reprog_idx=None)
    registry.register(WPID, device)

    event = DivertEvent(slot=1, pid=PID, wpid=WPID, cids={0x00D1})
    sub.notify(event)

    topics["write_topic"].publish.assert_not_called()


def test_divert_false_publishes_write_events():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DivertSubscriber(registry, topics)

    device = _make_device()
    registry.register(WPID, device)

    event = DivertEvent(slot=1, pid=PID, wpid=WPID, cids={0x00D1}, divert=False)
    sub.notify(event)

    assert topics["write_topic"].publish.call_count == 1


def test_divert_ignores_non_divert_event():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DivertSubscriber(registry, topics)
    sub.notify("not an event")  # must not raise
