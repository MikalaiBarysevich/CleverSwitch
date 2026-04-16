"""Unit tests for subscriber/host_change_subscriber.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from cleverswitch.event.host_change_event import HostChangeEvent
from cleverswitch.event.write_event import WriteEvent
from cleverswitch.hidpp.constants import BOLT_PID, FEATURE_CHANGE_HOST
from cleverswitch.model.logi_device import LogiDevice
from cleverswitch.registry.logi_device_registry import LogiDeviceRegistry
from cleverswitch.subscriber.host_change_subscriber import HostChangeSubscriber
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics

PID = BOLT_PID
WPID_KB = 0x407B
WPID_MOUSE = 0x4082
CHANGE_HOST_IDX = 9


def _make_topics():
    return Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        flags=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
    )


def _make_device(wpid, slot, role, change_host_idx=CHANGE_HOST_IDX):
    features = {FEATURE_CHANGE_HOST: change_host_idx}
    return LogiDevice(wpid=wpid, pid=PID, slot=slot, role=role, available_features=features, name=role)


def test_host_change_sends_to_all_devices():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = HostChangeSubscriber(registry, topics)

    kb = _make_device(WPID_KB, slot=1, role="keyboard")
    mouse = _make_device(WPID_MOUSE, slot=2, role="mouse")
    registry.register(WPID_KB, kb)
    registry.register(WPID_MOUSE, mouse)

    sub.notify(HostChangeEvent(slot=1, pid=PID, target_host=0))

    assert topics.write.publish.call_count == 2
    for call in topics.write.publish.call_args_list:
        assert isinstance(call[0][0], WriteEvent)


def test_host_change_skips_device_without_change_host():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = HostChangeSubscriber(registry, topics)

    kb = _make_device(WPID_KB, slot=1, role="keyboard")
    no_ch = LogiDevice(wpid=0x9999, pid=PID, slot=3, role="mouse", available_features={}, name="no-ch")
    registry.register(WPID_KB, kb)
    registry.register(0x9999, no_ch)

    sub.notify(HostChangeEvent(slot=1, pid=PID, target_host=0))

    assert topics.write.publish.call_count == 1


def test_host_change_ignores_non_host_change_event():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = HostChangeSubscriber(registry, topics)
    sub.notify("not a host change event")
    topics.write.publish.assert_not_called()
