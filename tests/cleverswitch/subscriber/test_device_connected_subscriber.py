"""Unit tests for subscriber/device_connected_subscriber.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from cleverswitch.event.device_connected_event import DeviceConnectedEvent
from cleverswitch.event.device_info_request_event import DeviceInfoRequestEvent
from cleverswitch.event.divert_event import DivertEvent
from cleverswitch.hidpp.constants import BOLT_PID, FEATURE_CHANGE_HOST, FEATURE_REPROG_CONTROLS_V4
from cleverswitch.model.logi_device import LogiDevice
from cleverswitch.registry.logi_device_registry import LogiDeviceRegistry
from cleverswitch.subscriber.device_connected_subscriber import DeviceConnectionSubscriber
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics

PID = BOLT_PID
WPID = 0x407B


def _make_topics():
    return Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        divert=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
    )


def _make_device(role="keyboard", divertable_cids=None, pending_steps=None):
    device = LogiDevice(
        wpid=WPID, pid=PID, slot=1, role=role,
        available_features={FEATURE_REPROG_CONTROLS_V4: 8, FEATURE_CHANGE_HOST: 9},
        divertable_cids=divertable_cids or set(),
    )
    if pending_steps is not None:
        device.pending_steps = pending_steps
    return device


# ── New connection ───────────────────────────────────────────────────────────


def test_new_connection_registers_device():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DeviceConnectionSubscriber(registry, topics)

    event = DeviceConnectedEvent(slot=1, pid=PID, link_established=True, wpid=WPID, device_type=1)
    sub.notify(event)

    device = registry.get_by_wpid(WPID)
    assert device is not None
    assert device.role == "keyboard"


def test_new_connection_publishes_device_info_request():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DeviceConnectionSubscriber(registry, topics)

    event = DeviceConnectedEvent(slot=1, pid=PID, link_established=True, wpid=WPID, device_type=None)
    sub.notify(event)

    topics.device_info.publish.assert_called_once()
    info_event = topics.device_info.publish.call_args[0][0]
    assert isinstance(info_event, DeviceInfoRequestEvent)
    assert info_event.type is True  # device_type unknown


def test_new_connection_with_known_type_sets_type_false():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DeviceConnectionSubscriber(registry, topics)

    event = DeviceConnectedEvent(slot=1, pid=PID, link_established=True, wpid=WPID, device_type=1)
    sub.notify(event)

    info_event = topics.device_info.publish.call_args[0][0]
    assert info_event.type is False


def test_new_connection_device_type_not_1_is_mouse():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DeviceConnectionSubscriber(registry, topics)

    event = DeviceConnectedEvent(slot=2, pid=PID, link_established=True, wpid=0x1234, device_type=3)
    sub.notify(event)

    device = registry.get_by_wpid(0x1234)
    assert device.role == "mouse"


# ── Reconnection ─────────────────────────────────────────────────────────────


def test_reconnection_rediverts_if_has_cids_and_reprog():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DeviceConnectionSubscriber(registry, topics)

    device = _make_device(divertable_cids={0x00D1, 0x00D2})
    device.pending_steps = set()
    registry.register(WPID, device)

    event = DeviceConnectedEvent(slot=1, pid=PID, link_established=True, wpid=WPID, device_type=1)
    sub.notify(event)

    topics.divert.publish.assert_called_once()
    divert_event = topics.divert.publish.call_args[0][0]
    assert isinstance(divert_event, DivertEvent)
    assert divert_event.cids == {0x00D1, 0x00D2}


def test_reconnection_does_not_divert_on_disconnect():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DeviceConnectionSubscriber(registry, topics)

    device = _make_device(divertable_cids={0x00D1})
    device.pending_steps = set()
    registry.register(WPID, device)

    event = DeviceConnectedEvent(slot=1, pid=PID, link_established=False, wpid=WPID, device_type=1)
    sub.notify(event)

    topics.divert.publish.assert_not_called()


def test_reconnection_requests_info_if_pending_steps():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DeviceConnectionSubscriber(registry, topics)

    device = _make_device(pending_steps={"resolve_reprog"})
    registry.register(WPID, device)

    event = DeviceConnectedEvent(slot=1, pid=PID, link_established=True, wpid=WPID, device_type=1)
    sub.notify(event)

    topics.device_info.publish.assert_called_once()


def test_reconnection_does_not_request_info_if_setup_complete():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DeviceConnectionSubscriber(registry, topics)

    device = _make_device(pending_steps=set())
    registry.register(WPID, device)

    event = DeviceConnectedEvent(slot=1, pid=PID, link_established=True, wpid=WPID, device_type=1)
    sub.notify(event)

    topics.device_info.publish.assert_not_called()


# ── connected flag ───────────────────────────────────────────────────────────


def test_sets_connected_false_on_disconnect():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DeviceConnectionSubscriber(registry, topics)

    device = _make_device()
    device.connected = True
    registry.register(WPID, device)

    event = DeviceConnectedEvent(slot=1, pid=PID, link_established=False, wpid=WPID, device_type=1)
    sub.notify(event)

    assert device.connected is False


def test_sets_connected_true_on_reconnect():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DeviceConnectionSubscriber(registry, topics)

    device = _make_device(pending_steps=set())
    device.connected = False
    registry.register(WPID, device)

    event = DeviceConnectedEvent(slot=1, pid=PID, link_established=True, wpid=WPID, device_type=1)
    sub.notify(event)

    assert device.connected is True


# ── Ignored events ───────────────────────────────────────────────────────────


def test_non_device_connected_event_ignored():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DeviceConnectionSubscriber(registry, topics)
    sub.notify("not an event")  # must not raise
