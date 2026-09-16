"""Tests for PeerHostFollowSubscriber — symmetric two-host fallback when x1814 never announces a switch."""

from unittest.mock import MagicMock

import pytest

from cleverswitch.event.device_connected_event import DeviceConnectedEvent
from cleverswitch.event.host_change_event import HostChangeEvent
from cleverswitch.hidpp.constants import BOLT_PID
from cleverswitch.model.config.easy_switch_config import EasySwitchConfig
from cleverswitch.model.logi_device import LogiDevice
from cleverswitch.registry.logi_device_registry import LogiDeviceRegistry
from cleverswitch.subscriber.peer_host_follow_subscriber import PeerHostFollowSubscriber
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics

PID = BOLT_PID
KEYBOARD_SLOT = 1
MOUSE_SLOT = 2
KEYBOARD_WPID = 0xB378
MOUSE_WPID = 0xB37A

# Deliberately different per role — proves the lookup uses the peer's own role, not a single
# shared index (each device keeps an independent host pairing table).
KEYBOARD_PEER_INDEX = 2
MOUSE_PEER_INDEX = 1
PEER_HOST_INDEX_BY_ROLE = {"keyboard": KEYBOARD_PEER_INDEX, "mouse": MOUSE_PEER_INDEX}


def _make_keyboard(*, slot: int = KEYBOARD_SLOT, pid: int = PID, wpid: int = KEYBOARD_WPID) -> LogiDevice:
    return LogiDevice(wpid=wpid, pid=pid, slot=slot, role="keyboard", available_features={}, friendly_name="MX KEYS S")


def _make_mouse(
    *, slot: int = MOUSE_SLOT, pid: int = PID, wpid: int = MOUSE_WPID, connected: bool = True
) -> LogiDevice:
    return LogiDevice(
        wpid=wpid,
        pid=pid,
        slot=slot,
        role="mouse",
        available_features={},
        friendly_name="MX Ergo S",
        connected=connected,
    )


def _make_event(
    *, slot: int = KEYBOARD_SLOT, pid: int = PID, wpid: int = KEYBOARD_WPID, link_established: bool = False
) -> DeviceConnectedEvent:
    return DeviceConnectedEvent(slot=slot, pid=pid, wpid=wpid, link_established=link_established, device_type=0)


@pytest.fixture
def registry() -> LogiDeviceRegistry:
    return LogiDeviceRegistry()


@pytest.fixture
def topics() -> Topics:
    return Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        flags=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
    )


@pytest.fixture
def subscriber(registry, topics) -> PeerHostFollowSubscriber:
    return PeerHostFollowSubscriber(registry, topics, EasySwitchConfig(peer_host_index=PEER_HOST_INDEX_BY_ROLE))


def _connect(subscriber, *, slot: int, wpid: int) -> None:
    """A disconnect only triggers the relay after this subscriber has locally observed a connect
    for the same wpid — otherwise the gateway's startup enumeration (reporting whatever is
    already, legitimately, paired elsewhere as "disconnected") would falsely look like a fresh
    departure. Every test that wants a genuine departure must connect first."""
    subscriber.notify(_make_event(slot=slot, wpid=wpid, link_established=True))


class TestPeerHostFollowSubscriber:
    def test_keyboard_disconnect_with_connected_mouse_uses_mouse_configured_index(self, subscriber, registry, topics):
        registry.register(KEYBOARD_WPID, _make_keyboard())
        registry.register(MOUSE_WPID, _make_mouse())
        _connect(subscriber, slot=KEYBOARD_SLOT, wpid=KEYBOARD_WPID)
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event())

        topics.hid_event.publish.assert_called_once()
        event = topics.hid_event.publish.call_args[0][0]
        assert isinstance(event, HostChangeEvent)
        assert event.target_host == MOUSE_PEER_INDEX
        assert event.slot == KEYBOARD_SLOT
        assert event.pid == PID

    def test_mouse_disconnect_with_connected_keyboard_uses_keyboard_configured_index(
        self, subscriber, registry, topics
    ):
        """Symmetric on purpose — unlike Logitech's own keyboard-only Enhanced Easy-Switch, this
        fallback lets either device drive the relay, since the mouse only has two host slots.
        Also proves the per-role lookup: the keyboard's own index is used, not the mouse's."""
        registry.register(KEYBOARD_WPID, _make_keyboard())
        registry.register(MOUSE_WPID, _make_mouse())
        _connect(subscriber, slot=MOUSE_SLOT, wpid=MOUSE_WPID)
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event(slot=MOUSE_SLOT, wpid=MOUSE_WPID))

        topics.hid_event.publish.assert_called_once()
        event = topics.hid_event.publish.call_args[0][0]
        assert isinstance(event, HostChangeEvent)
        assert event.target_host == KEYBOARD_PEER_INDEX
        assert event.slot == MOUSE_SLOT
        assert event.pid == PID

    def test_keyboard_reconnect_is_ignored(self, subscriber, registry, topics):
        registry.register(KEYBOARD_WPID, _make_keyboard())
        registry.register(MOUSE_WPID, _make_mouse())
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event(link_established=True))

        topics.hid_event.publish.assert_not_called()

    def test_disconnect_without_prior_local_connect_is_ignored(self, subscriber, registry, topics):
        """The startup-enumeration case: a device already paired elsewhere is reported disconnected
        the first time this daemon ever hears about it — not a genuine departure."""
        registry.register(KEYBOARD_WPID, _make_keyboard())
        registry.register(MOUSE_WPID, _make_mouse())
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event())

        topics.hid_event.publish.assert_not_called()

    def test_disconnect_with_no_configured_roles_ignored(self, registry, topics):
        subscriber = PeerHostFollowSubscriber(registry, topics, EasySwitchConfig(peer_host_index={}))
        registry.register(KEYBOARD_WPID, _make_keyboard())
        registry.register(MOUSE_WPID, _make_mouse())
        _connect(subscriber, slot=KEYBOARD_SLOT, wpid=KEYBOARD_WPID)
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event())

        topics.hid_event.publish.assert_not_called()

    def test_disconnect_with_peer_role_not_in_config_ignored(self, registry, topics):
        """Only the mouse's role is configured — a keyboard departure has no mouse index to use,
        so it must not fall back to the keyboard's own (differently-scoped) index."""
        subscriber = PeerHostFollowSubscriber(registry, topics, EasySwitchConfig(peer_host_index={"keyboard": 2}))
        registry.register(KEYBOARD_WPID, _make_keyboard())
        registry.register(MOUSE_WPID, _make_mouse())
        _connect(subscriber, slot=KEYBOARD_SLOT, wpid=KEYBOARD_WPID)
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event())

        topics.hid_event.publish.assert_not_called()

    def test_keyboard_disconnect_with_disconnected_mouse_ignored(self, subscriber, registry, topics):
        registry.register(KEYBOARD_WPID, _make_keyboard())
        registry.register(MOUSE_WPID, _make_mouse(connected=False))
        _connect(subscriber, slot=KEYBOARD_SLOT, wpid=KEYBOARD_WPID)
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event())

        topics.hid_event.publish.assert_not_called()

    def test_keyboard_disconnect_without_registered_mouse_ignored(self, subscriber, registry, topics):
        registry.register(KEYBOARD_WPID, _make_keyboard())
        _connect(subscriber, slot=KEYBOARD_SLOT, wpid=KEYBOARD_WPID)
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event())

        topics.hid_event.publish.assert_not_called()

    def test_unknown_device_ignored(self, subscriber, topics):
        _connect(subscriber, slot=KEYBOARD_SLOT, wpid=KEYBOARD_WPID)
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event())

        topics.hid_event.publish.assert_not_called()

    def test_departed_device_without_role_ignored(self, subscriber, registry, topics):
        """A connection blip before device-type discovery completes has no role yet."""
        registry.register(
            KEYBOARD_WPID,
            LogiDevice(wpid=KEYBOARD_WPID, pid=PID, slot=KEYBOARD_SLOT, role=None, available_features={}),
        )
        registry.register(MOUSE_WPID, _make_mouse())
        _connect(subscriber, slot=KEYBOARD_SLOT, wpid=KEYBOARD_WPID)
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event())

        topics.hid_event.publish.assert_not_called()

    def test_other_pid_ignored(self, subscriber, registry, topics):
        registry.register(KEYBOARD_WPID, _make_keyboard(pid=0xC52B))
        registry.register(MOUSE_WPID, _make_mouse())
        _connect(subscriber, slot=KEYBOARD_SLOT, wpid=KEYBOARD_WPID)
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event(pid=PID))

        topics.hid_event.publish.assert_not_called()

    def test_mouse_on_different_pid_not_matched_as_peer(self, subscriber, registry, topics):
        """Bluetooth-direct devices never share a pid — must not be picked as a false peer."""
        registry.register(KEYBOARD_WPID, _make_keyboard())
        registry.register(MOUSE_WPID, _make_mouse(pid=0xC52B))
        _connect(subscriber, slot=KEYBOARD_SLOT, wpid=KEYBOARD_WPID)
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event())

        topics.hid_event.publish.assert_not_called()

    def test_non_device_connected_event_ignored(self, subscriber, registry, topics):
        registry.register(KEYBOARD_WPID, _make_keyboard())
        registry.register(MOUSE_WPID, _make_mouse())
        _connect(subscriber, slot=KEYBOARD_SLOT, wpid=KEYBOARD_WPID)
        topics.hid_event.publish.reset_mock()

        subscriber.notify("not a DeviceConnectedEvent")

        topics.hid_event.publish.assert_not_called()

    def test_second_consecutive_disconnect_is_ignored(self, subscriber, registry, topics):
        """A duplicate disconnect notification (no intervening reconnect) must not re-fire."""
        registry.register(KEYBOARD_WPID, _make_keyboard())
        registry.register(MOUSE_WPID, _make_mouse())
        _connect(subscriber, slot=KEYBOARD_SLOT, wpid=KEYBOARD_WPID)
        subscriber.notify(_make_event())
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event())

        topics.hid_event.publish.assert_not_called()

    def test_subscribes_to_hid_event_topic(self, registry, topics):
        subscriber = PeerHostFollowSubscriber(registry, topics, EasySwitchConfig(peer_host_index={}))

        topics.hid_event.subscribe.assert_called_once_with(subscriber)
