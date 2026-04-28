"""Unit tests for subscriber/transport_disconnection_subscriber.py."""

from __future__ import annotations

from unittest.mock import MagicMock, call

from src.cleverswitch.event.device_connected_event import DeviceConnectedEvent
from src.cleverswitch.event.transport_disconnected_event import TransportDisconnectedEvent
from src.cleverswitch.hidpp.constants import BOLT_PID
from src.cleverswitch.model.logi_device import LogiDevice
from src.cleverswitch.registry.logi_device_registry import LogiDeviceRegistry
from src.cleverswitch.subscriber.transport_disconnection_subscriber import TransportDisconnectionSubscriber
from src.cleverswitch.topic.topic import Topic
from src.cleverswitch.topic.topics import Topics

PID = BOLT_PID
OTHER_PID = 0xC549  # a pid distinct from BOLT_PID
WPID_KB = 0x407B
WPID_MOUSE = 0xB012


def _make_topics():
    return Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        flags=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
    )


def _make_device(wpid: int, pid: int = PID, slot: int = 1, role: str = "keyboard") -> LogiDevice:
    return LogiDevice(wpid=wpid, pid=pid, slot=slot, role=role, available_features={})


def _transport_disconnected(pid: int = PID) -> TransportDisconnectedEvent:
    return TransportDisconnectedEvent(slot=0, pid=pid)


# ── Fan-out ──────────────────────────────────────────────────────────────────


def test_fan_out_emits_disconnect_event_per_matching_device():
    registry = LogiDeviceRegistry()
    registry.register(WPID_KB, _make_device(WPID_KB, slot=1))
    registry.register(WPID_MOUSE, _make_device(WPID_MOUSE, slot=2, role="mouse"))

    topics = _make_topics()
    sub = TransportDisconnectionSubscriber(registry, topics)

    sub.notify(_transport_disconnected(PID))

    assert topics.hid_event.publish.call_count == 2
    published_events = [c.args[0] for c in topics.hid_event.publish.call_args_list]
    wpids = {e.wpid for e in published_events}
    assert wpids == {WPID_KB, WPID_MOUSE}
    for event in published_events:
        assert isinstance(event, DeviceConnectedEvent)
        assert event.link_established is False
        assert event.device_type is None


def test_fan_out_sets_correct_slot_and_pid():
    registry = LogiDeviceRegistry()
    registry.register(WPID_KB, _make_device(WPID_KB, pid=PID, slot=3))

    topics = _make_topics()
    sub = TransportDisconnectionSubscriber(registry, topics)

    sub.notify(_transport_disconnected(PID))

    published = topics.hid_event.publish.call_args[0][0]
    assert published.slot == 3
    assert published.pid == PID
    assert published.wpid == WPID_KB


# ── Ignore other pids ────────────────────────────────────────────────────────


def test_ignores_devices_with_different_pid():
    registry = LogiDeviceRegistry()
    registry.register(WPID_KB, _make_device(WPID_KB, pid=OTHER_PID, slot=1))

    topics = _make_topics()
    sub = TransportDisconnectionSubscriber(registry, topics)

    sub.notify(_transport_disconnected(PID))

    topics.hid_event.publish.assert_not_called()


def test_partial_fan_out_when_mixed_pids():
    registry = LogiDeviceRegistry()
    registry.register(WPID_KB, _make_device(WPID_KB, pid=PID, slot=1))
    registry.register(WPID_MOUSE, _make_device(WPID_MOUSE, pid=OTHER_PID, slot=2, role="mouse"))

    topics = _make_topics()
    sub = TransportDisconnectionSubscriber(registry, topics)

    sub.notify(_transport_disconnected(PID))

    assert topics.hid_event.publish.call_count == 1
    published = topics.hid_event.publish.call_args[0][0]
    assert published.wpid == WPID_KB


# ── Empty registry ───────────────────────────────────────────────────────────


def test_empty_registry_no_op():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = TransportDisconnectionSubscriber(registry, topics)

    sub.notify(_transport_disconnected(PID))

    topics.hid_event.publish.assert_not_called()


# ── Non-TransportDisconnectedEvent ignored ───────────────────────────────────


def test_non_transport_disconnected_event_ignored():
    registry = LogiDeviceRegistry()
    registry.register(WPID_KB, _make_device(WPID_KB))

    topics = _make_topics()
    sub = TransportDisconnectionSubscriber(registry, topics)

    sub.notify("not a transport event")
    sub.notify(DeviceConnectedEvent(slot=1, pid=PID, link_established=False, wpid=WPID_KB))

    topics.hid_event.publish.assert_not_called()
