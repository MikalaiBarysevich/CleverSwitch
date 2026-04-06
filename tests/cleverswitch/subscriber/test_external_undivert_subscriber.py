"""Unit tests for subscriber/external_undivert_subscriber.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from cleverswitch.event.divert_event import DivertEvent
from cleverswitch.event.external_undivert_event import ExternalUndivertEvent
from cleverswitch.hidpp.constants import BOLT_PID, FEATURE_CHANGE_HOST, FEATURE_REPROG_CONTROLS_V4
from cleverswitch.model.logi_device import LogiDevice
from cleverswitch.registry.logi_device_registry import LogiDeviceRegistry
from cleverswitch.subscriber.external_undivert_subscriber import ExternalUndivertSubscriber
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics

PID = BOLT_PID
REPROG_IDX = 8


def _make_topics():
    return Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        divert=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
    )


def _make_device(slot=1, reprog_idx=REPROG_IDX, divertable_cids=None):
    features = {FEATURE_CHANGE_HOST: 9}
    if reprog_idx is not None:
        features[FEATURE_REPROG_CONTROLS_V4] = reprog_idx
    return LogiDevice(
        wpid=0x407B, pid=PID, slot=slot, role="keyboard",
        available_features=features,
        divertable_cids=divertable_cids or {0x00D1, 0x00D2, 0x00D3},
    )


def test_external_undivert_rediverts_single_cid():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = ExternalUndivertSubscriber(registry, topics)

    device = _make_device()
    registry.register(0x407B, device)

    event = ExternalUndivertEvent(slot=1, pid=PID, feature_index=REPROG_IDX, cid=0x00D1)
    sub.notify(event)

    topics.divert.publish.assert_called_once()
    divert_event = topics.divert.publish.call_args[0][0]
    assert isinstance(divert_event, DivertEvent)
    assert divert_event.cids == {0x00D1}


def test_external_undivert_ignores_unknown_device():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = ExternalUndivertSubscriber(registry, topics)

    event = ExternalUndivertEvent(slot=5, pid=PID, feature_index=REPROG_IDX, cid=0x00D1)
    sub.notify(event)

    topics.divert.publish.assert_not_called()


def test_external_undivert_ignores_wrong_feature_index():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = ExternalUndivertSubscriber(registry, topics)

    device = _make_device()
    registry.register(0x407B, device)

    event = ExternalUndivertEvent(slot=1, pid=PID, feature_index=99, cid=0x00D1)
    sub.notify(event)

    topics.divert.publish.assert_not_called()


def test_external_undivert_ignores_non_divertable_cid():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = ExternalUndivertSubscriber(registry, topics)

    device = _make_device(divertable_cids={0x00D1})
    registry.register(0x407B, device)

    event = ExternalUndivertEvent(slot=1, pid=PID, feature_index=REPROG_IDX, cid=0x00D2)
    sub.notify(event)

    topics.divert.publish.assert_not_called()


def test_external_undivert_ignores_device_without_reprog():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = ExternalUndivertSubscriber(registry, topics)

    device = _make_device(reprog_idx=None)
    registry.register(0x407B, device)

    event = ExternalUndivertEvent(slot=1, pid=PID, feature_index=8, cid=0x00D1)
    sub.notify(event)

    topics.divert.publish.assert_not_called()


def test_external_undivert_ignores_non_external_undivert_event():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = ExternalUndivertSubscriber(registry, topics)
    sub.notify("not an event")  # must not raise
