"""Unit tests for subscriber/diverted_host_change_subscriber.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from cleverswitch.event.hidpp_notification_event import HidppNotificationEvent
from cleverswitch.event.write_event import WriteEvent
from cleverswitch.hidpp.constants import BOLT_PID, FEATURE_CHANGE_HOST, FEATURE_REPROG_CONTROLS_V4
from cleverswitch.model.logi_device import LogiDevice
from cleverswitch.registry.logi_device_registry import LogiDeviceRegistry
from cleverswitch.subscriber.diverted_host_change_subscriber import DivertedHostChangeSubscriber
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics

PID = BOLT_PID
WPID_KB = 0x407B
WPID_MOUSE = 0x4082
REPROG_IDX = 8
CHANGE_HOST_IDX = 9


def _make_topics():
    return Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        divert=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
    )


def _make_device(wpid, slot, role, change_host_idx=CHANGE_HOST_IDX, reprog_idx=None):
    features = {FEATURE_CHANGE_HOST: change_host_idx}
    if reprog_idx is not None:
        features[FEATURE_REPROG_CONTROLS_V4] = reprog_idx
    return LogiDevice(wpid=wpid, pid=PID, slot=slot, role=role, available_features=features, name=role)


def _host_switch_notification(slot, reprog_idx, cid_hi, cid_lo):
    payload = bytes([cid_hi, cid_lo]) + bytes(14)
    return HidppNotificationEvent(slot=slot, pid=PID, feature_index=reprog_idx, function=0, payload=payload)


def test_diverted_host_change_sends_to_all_devices():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DivertedHostChangeSubscriber(registry, topics)

    kb = _make_device(WPID_KB, slot=1, role="keyboard", reprog_idx=REPROG_IDX)
    mouse = _make_device(WPID_MOUSE, slot=2, role="mouse")
    registry.register(WPID_KB, kb)
    registry.register(WPID_MOUSE, mouse)

    event = _host_switch_notification(slot=1, reprog_idx=REPROG_IDX, cid_hi=0x00, cid_lo=0xD1)
    sub.notify(event)

    # Should send to ALL devices (including source, since key was diverted)
    assert topics.write.publish.call_count == 2
    for call in topics.write.publish.call_args_list:
        assert isinstance(call[0][0], WriteEvent)


def test_diverted_host_change_ignores_non_reprog_feature():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DivertedHostChangeSubscriber(registry, topics)

    kb = _make_device(WPID_KB, slot=1, role="keyboard", reprog_idx=REPROG_IDX)
    registry.register(WPID_KB, kb)

    event = HidppNotificationEvent(slot=1, pid=PID, feature_index=99, function=0, payload=bytes(16))
    sub.notify(event)

    topics.write.publish.assert_not_called()


def test_diverted_host_change_ignores_non_easy_switch_cid():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DivertedHostChangeSubscriber(registry, topics)

    kb = _make_device(WPID_KB, slot=1, role="keyboard", reprog_idx=REPROG_IDX)
    registry.register(WPID_KB, kb)

    event = _host_switch_notification(slot=1, reprog_idx=REPROG_IDX, cid_hi=0x00, cid_lo=0xAA)
    sub.notify(event)

    topics.write.publish.assert_not_called()


def test_diverted_host_change_ignores_unknown_device():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DivertedHostChangeSubscriber(registry, topics)

    event = _host_switch_notification(slot=1, reprog_idx=REPROG_IDX, cid_hi=0x00, cid_lo=0xD1)
    sub.notify(event)

    topics.write.publish.assert_not_called()


def test_diverted_host_change_ignores_non_zero_function():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DivertedHostChangeSubscriber(registry, topics)

    kb = _make_device(WPID_KB, slot=1, role="keyboard", reprog_idx=REPROG_IDX)
    registry.register(WPID_KB, kb)

    event = HidppNotificationEvent(slot=1, pid=PID, feature_index=REPROG_IDX, function=1, payload=bytes(16))
    sub.notify(event)

    topics.write.publish.assert_not_called()


def test_diverted_host_change_ignores_non_notification_event():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DivertedHostChangeSubscriber(registry, topics)
    sub.notify("not a notification")  # must not raise


def test_diverted_host_change_skips_device_without_change_host():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DivertedHostChangeSubscriber(registry, topics)

    kb = _make_device(WPID_KB, slot=1, role="keyboard", reprog_idx=REPROG_IDX)
    no_ch = LogiDevice(wpid=0x9999, pid=PID, slot=3, role="mouse", available_features={}, name="no-ch")
    registry.register(WPID_KB, kb)
    registry.register(0x9999, no_ch)

    event = _host_switch_notification(slot=1, reprog_idx=REPROG_IDX, cid_hi=0x00, cid_lo=0xD1)
    sub.notify(event)

    # Only 1 write (kb has CHANGE_HOST, no_ch doesn't)
    assert topics.write.publish.call_count == 1
