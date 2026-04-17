"""Unit tests for subscriber/event_hook_subscriber.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cleverswitch.event.device_connected_event import DeviceConnectedEvent
from cleverswitch.event.host_change_event import HostChangeEvent
from cleverswitch.hidpp.constants import BOLT_PID
from cleverswitch.model.config.hooks_config import HooksConfig
from cleverswitch.model.logi_device import LogiDevice
from cleverswitch.registry.logi_device_registry import LogiDeviceRegistry
from cleverswitch.subscriber.event_hook_subscriber import EventHookSubscriber
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics

PID = BOLT_PID
WPID = 0x407B


def _make_topics():
    return Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        flags=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
    )


def _make_device(wpid=WPID, slot=1, role="keyboard", name="MX Keys"):
    return LogiDevice(wpid=wpid, pid=PID, slot=slot, role=role, available_features={}, name=name)


def _hooks_cfg():
    return HooksConfig()


# ── Connect ──────────────────────────────────────────────────────────────────


@patch("cleverswitch.subscriber.event_hook_subscriber.hooks")
def test_connect_fires_for_known_device(mock_hooks):
    registry = LogiDeviceRegistry()
    device = _make_device()
    registry.register(WPID, device)

    sub = EventHookSubscriber(_hooks_cfg(), registry, _make_topics())
    sub.notify(DeviceConnectedEvent(slot=1, pid=PID, link_established=True, wpid=WPID))

    mock_hooks.fire_connect.assert_called_once_with(_hooks_cfg(), "MX Keys", "keyboard")


@patch("cleverswitch.subscriber.event_hook_subscriber.hooks")
def test_connect_skipped_for_unknown_device(mock_hooks):
    sub = EventHookSubscriber(_hooks_cfg(), LogiDeviceRegistry(), _make_topics())
    sub.notify(DeviceConnectedEvent(slot=1, pid=PID, link_established=True, wpid=WPID))

    mock_hooks.fire_connect.assert_not_called()


@patch("cleverswitch.subscriber.event_hook_subscriber.hooks")
def test_connect_skipped_when_name_is_none(mock_hooks):
    registry = LogiDeviceRegistry()
    device = _make_device(name=None)
    registry.register(WPID, device)

    sub = EventHookSubscriber(_hooks_cfg(), registry, _make_topics())
    sub.notify(DeviceConnectedEvent(slot=1, pid=PID, link_established=True, wpid=WPID))

    mock_hooks.fire_connect.assert_not_called()


@patch("cleverswitch.subscriber.event_hook_subscriber.hooks")
def test_connect_skipped_when_role_is_none(mock_hooks):
    registry = LogiDeviceRegistry()
    device = _make_device(role=None)
    registry.register(WPID, device)

    sub = EventHookSubscriber(_hooks_cfg(), registry, _make_topics())
    sub.notify(DeviceConnectedEvent(slot=1, pid=PID, link_established=True, wpid=WPID))

    mock_hooks.fire_connect.assert_not_called()


# ── Disconnect ───────────────────────────────────────────────────────────────


@patch("cleverswitch.subscriber.event_hook_subscriber.hooks")
def test_disconnect_fires_for_known_device(mock_hooks):
    registry = LogiDeviceRegistry()
    device = _make_device()
    registry.register(WPID, device)

    sub = EventHookSubscriber(_hooks_cfg(), registry, _make_topics())
    sub.notify(DeviceConnectedEvent(slot=1, pid=PID, link_established=False, wpid=WPID))

    mock_hooks.fire_disconnect.assert_called_once_with(_hooks_cfg(), "MX Keys", "keyboard")


@patch("cleverswitch.subscriber.event_hook_subscriber.hooks")
def test_disconnect_skipped_for_unknown_device(mock_hooks):
    sub = EventHookSubscriber(_hooks_cfg(), LogiDeviceRegistry(), _make_topics())
    sub.notify(DeviceConnectedEvent(slot=1, pid=PID, link_established=False, wpid=WPID))

    mock_hooks.fire_disconnect.assert_not_called()


# ── Host Change ──────────────────────────────────────────────────────────────


@patch("cleverswitch.subscriber.event_hook_subscriber.hooks")
def test_host_change_fires_for_known_device(mock_hooks):
    registry = LogiDeviceRegistry()
    device = _make_device()
    registry.register(WPID, device)

    sub = EventHookSubscriber(_hooks_cfg(), registry, _make_topics())
    sub.notify(HostChangeEvent(slot=1, pid=PID, target_host=2))

    mock_hooks.fire_switch.assert_called_once_with(_hooks_cfg(), "MX Keys", "keyboard", 2)


@patch("cleverswitch.subscriber.event_hook_subscriber.hooks")
def test_host_change_skipped_for_unknown_device(mock_hooks):
    sub = EventHookSubscriber(_hooks_cfg(), LogiDeviceRegistry(), _make_topics())
    sub.notify(HostChangeEvent(slot=1, pid=PID, target_host=0))

    mock_hooks.fire_switch.assert_not_called()


# ── Irrelevant events ───────────────────────────────────────────────────────


@patch("cleverswitch.subscriber.event_hook_subscriber.hooks")
def test_ignores_non_relevant_events(mock_hooks):
    sub = EventHookSubscriber(_hooks_cfg(), LogiDeviceRegistry(), _make_topics())
    sub.notify("some other event")

    mock_hooks.fire_connect.assert_not_called()
    mock_hooks.fire_disconnect.assert_not_called()
    mock_hooks.fire_switch.assert_not_called()
