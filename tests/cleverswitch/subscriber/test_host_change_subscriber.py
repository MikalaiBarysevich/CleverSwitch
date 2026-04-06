"""Unit tests for subscriber/host_change_subscriber.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from cleverswitch.event.hidpp_notification_event import HidppNotificationEvent
from cleverswitch.event.write_event import WriteEvent
from cleverswitch.hidpp.constants import BOLT_PID, FEATURE_CHANGE_HOST
from cleverswitch.model.logi_device import LogiDevice
from cleverswitch.registry.logi_device_registry import LogiDeviceRegistry
from cleverswitch.subscriber.host_change_subscriber import HostChangeSubscriber
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics

PID = BOLT_PID
CHANGE_HOST_IDX = 9


def _make_topics():
    return Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        divert=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
    )


def _make_device(wpid, slot, role="mouse"):
    return LogiDevice(
        wpid=wpid, pid=PID, slot=slot, role=role,
        available_features={FEATURE_CHANGE_HOST: CHANGE_HOST_IDX},
        name=role,
    )


def _change_host_notification(slot, change_host_idx, target_host):
    payload = bytes([target_host]) + bytes(15)
    return HidppNotificationEvent(slot=slot, pid=PID, feature_index=change_host_idx, function=0, payload=payload)


def test_host_change_sends_to_other_devices():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = HostChangeSubscriber(registry, topics)

    mouse = _make_device(0x4082, slot=2, role="mouse")
    kb = _make_device(0x407B, slot=1, role="keyboard")
    registry.register(0x4082, mouse)
    registry.register(0x407B, kb)

    event = _change_host_notification(slot=2, change_host_idx=CHANGE_HOST_IDX, target_host=1)
    sub.notify(event)

    # Should only send to keyboard (not back to source mouse)
    assert topics.write.publish.call_count == 1
    write_event = topics.write.publish.call_args[0][0]
    assert isinstance(write_event, WriteEvent)
    assert write_event.slot == 1  # keyboard slot


def test_host_change_ignores_unknown_source_device():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = HostChangeSubscriber(registry, topics)

    event = _change_host_notification(slot=5, change_host_idx=CHANGE_HOST_IDX, target_host=0)
    sub.notify(event)

    topics.write.publish.assert_not_called()


def test_host_change_ignores_non_change_host_feature():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = HostChangeSubscriber(registry, topics)

    mouse = _make_device(0x4082, slot=2)
    registry.register(0x4082, mouse)

    event = HidppNotificationEvent(slot=2, pid=PID, feature_index=99, function=0, payload=bytes(16))
    sub.notify(event)

    topics.write.publish.assert_not_called()


def test_host_change_ignores_non_notification_event():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = HostChangeSubscriber(registry, topics)
    sub.notify("not an event")  # must not raise


def test_host_change_skips_device_without_change_host_feature():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = HostChangeSubscriber(registry, topics)

    source = _make_device(0x4082, slot=2)
    no_ch = LogiDevice(wpid=0x9999, pid=PID, slot=3, role="mouse", available_features={}, name="no-ch")
    registry.register(0x4082, source)
    registry.register(0x9999, no_ch)

    event = _change_host_notification(slot=2, change_host_idx=CHANGE_HOST_IDX, target_host=1)
    sub.notify(event)

    # no_ch has no CHANGE_HOST so should be skipped
    topics.write.publish.assert_not_called()
