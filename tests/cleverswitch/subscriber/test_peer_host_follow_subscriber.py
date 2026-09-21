"""Tests for PeerHostFollowSubscriber — symmetric two-host fallback when x1814 never announces a switch."""

import time
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
    return _make_subscriber(registry, topics, PEER_HOST_INDEX_BY_ROLE)


def _make_subscriber(registry, topics, peer_host_index: dict[str, int], *, delay: float = 0.0):
    """Delay defaults to 0 so the deferred relay lands as soon as the timer thread is scheduled.
    The delay exists to debounce RF micro-dropouts (a reconnect inside the window cancels the
    relay) and to let a slightly-late x1814 announcement overtake the disconnect (see the class
    docstring); tests that care about either behaviour set it explicitly."""
    return PeerHostFollowSubscriber(
        registry, topics, EasySwitchConfig(peer_host_index=peer_host_index), relay_delay_s=delay
    )


def _connect(subscriber, *, slot: int, wpid: int) -> None:
    """A disconnect only triggers the relay after this subscriber has locally observed a connect
    for the same wpid — otherwise the gateway's startup enumeration (reporting whatever is
    already, legitimately, paired elsewhere as "disconnected") would falsely look like a fresh
    departure. Every test that wants a genuine departure must connect first."""
    subscriber.notify(_make_event(slot=slot, wpid=wpid, link_established=True))


def _wait_for_publish(topics, *, timeout: float = 2.0) -> None:
    """The relay is published from a timer thread, so it is never visible synchronously."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if topics.hid_event.publish.called:
            return
        time.sleep(0.005)
    raise AssertionError("relay was never published")


def _assert_never_publishes(topics, *, grace: float = 0.1) -> None:
    """Suppression happens inside the timer callback, so 'not called' has to outlive the timer."""
    time.sleep(grace)
    topics.hid_event.publish.assert_not_called()


class TestPeerHostFollowSubscriber:
    def test_keyboard_disconnect_with_connected_mouse_uses_mouse_configured_index(self, subscriber, registry, topics):
        registry.register(KEYBOARD_WPID, _make_keyboard())
        registry.register(MOUSE_WPID, _make_mouse())
        _connect(subscriber, slot=KEYBOARD_SLOT, wpid=KEYBOARD_WPID)
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event())

        _wait_for_publish(topics)
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

        _wait_for_publish(topics)
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
        subscriber = _make_subscriber(registry, topics, {})
        registry.register(KEYBOARD_WPID, _make_keyboard())
        registry.register(MOUSE_WPID, _make_mouse())
        _connect(subscriber, slot=KEYBOARD_SLOT, wpid=KEYBOARD_WPID)
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event())

        topics.hid_event.publish.assert_not_called()

    def test_disconnect_with_peer_role_not_in_config_ignored(self, registry, topics):
        """Only the mouse's role is configured — a keyboard departure has no mouse index to use,
        so it must not fall back to the keyboard's own (differently-scoped) index."""
        subscriber = _make_subscriber(registry, topics, {"keyboard": 2})
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
        _wait_for_publish(topics)
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event())

        _assert_never_publishes(topics)

    def test_subscribes_to_hid_event_topic(self, registry, topics):
        subscriber = _make_subscriber(registry, topics, {})

        topics.hid_event.subscribe.assert_called_once_with(subscriber)


class TestAnnouncedSwitchSuppression:
    """A device whose x1814 (or CID) announcement does work is already relayed by
    ChangeHostNotificationSubscriber / HostChangeSubscriber. Relaying again on the disconnect
    that follows would send the peer to the configured index instead of the announced target —
    a visible bug on any setup with more than two hosts."""

    def test_announced_switch_suppresses_the_relay(self, subscriber, registry, topics):
        registry.register(KEYBOARD_WPID, _make_keyboard())
        registry.register(MOUSE_WPID, _make_mouse())
        _connect(subscriber, slot=KEYBOARD_SLOT, wpid=KEYBOARD_WPID)
        subscriber.notify(HostChangeEvent(slot=KEYBOARD_SLOT, pid=PID, target_host=0))
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event())

        _assert_never_publishes(topics)

    def test_announcement_from_one_device_suppresses_the_other_devices_disconnect(self, subscriber, registry, topics):
        """Suppression is not keyed per device on purpose: the keyboard announces, the mouse is
        commanded to follow, and then the mouse's own disconnect must not fire a second relay."""
        registry.register(KEYBOARD_WPID, _make_keyboard())
        registry.register(MOUSE_WPID, _make_mouse())
        _connect(subscriber, slot=MOUSE_SLOT, wpid=MOUSE_WPID)
        subscriber.notify(HostChangeEvent(slot=KEYBOARD_SLOT, pid=PID, target_host=0))
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event(slot=MOUSE_SLOT, wpid=MOUSE_WPID))

        _assert_never_publishes(topics)

    def test_own_relayed_event_does_not_suppress_the_next_relay(self, subscriber, registry, topics):
        """The relay's own HostChangeEvent comes back on this subscriber's queue. Treating it as
        an announcement would make the fallback disable itself after a single use."""
        registry.register(KEYBOARD_WPID, _make_keyboard())
        registry.register(MOUSE_WPID, _make_mouse())
        _connect(subscriber, slot=KEYBOARD_SLOT, wpid=KEYBOARD_WPID)
        subscriber.notify(_make_event())
        _wait_for_publish(topics)
        subscriber.notify(topics.hid_event.publish.call_args[0][0])
        topics.hid_event.publish.reset_mock()

        _connect(subscriber, slot=KEYBOARD_SLOT, wpid=KEYBOARD_WPID)
        subscriber.notify(_make_event())

        _wait_for_publish(topics)
        assert topics.hid_event.publish.call_args[0][0].target_host == MOUSE_PEER_INDEX

    def test_relay_fires_again_once_the_suppression_window_expires(self, subscriber, registry, topics, mocker):
        mocker.patch("cleverswitch.subscriber.peer_host_follow_subscriber.ANNOUNCED_SWITCH_WINDOW_S", 0.05)
        registry.register(KEYBOARD_WPID, _make_keyboard())
        registry.register(MOUSE_WPID, _make_mouse())
        _connect(subscriber, slot=KEYBOARD_SLOT, wpid=KEYBOARD_WPID)
        subscriber.notify(HostChangeEvent(slot=KEYBOARD_SLOT, pid=PID, target_host=0))
        topics.hid_event.publish.reset_mock()
        time.sleep(0.06)

        subscriber.notify(_make_event())

        _wait_for_publish(topics)
        topics.hid_event.publish.assert_called_once()

    def test_relay_is_deferred_not_published_inline(self, registry, topics):
        """The x1814 announcement is translated on another subscriber's thread, so it can arrive
        just after the disconnect. Publishing inline would lose that race irrecoverably."""
        subscriber = _make_subscriber(registry, topics, PEER_HOST_INDEX_BY_ROLE, delay=5.0)
        registry.register(KEYBOARD_WPID, _make_keyboard())
        registry.register(MOUSE_WPID, _make_mouse())
        _connect(subscriber, slot=KEYBOARD_SLOT, wpid=KEYBOARD_WPID)
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event())

        topics.hid_event.publish.assert_not_called()

    def test_peer_leaving_during_the_grace_period_cancels_the_relay(self, registry, topics):
        subscriber = _make_subscriber(registry, topics, PEER_HOST_INDEX_BY_ROLE, delay=0.2)
        mouse = _make_mouse()
        registry.register(KEYBOARD_WPID, _make_keyboard())
        registry.register(MOUSE_WPID, mouse)
        _connect(subscriber, slot=KEYBOARD_SLOT, wpid=KEYBOARD_WPID)
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event())
        mouse.connected = False

        _assert_never_publishes(topics, grace=0.4)


class TestReconnectDebounce:
    """An RF micro-dropout is reported as the same bare 0x41 disconnect as a genuine departure,
    but the dropped device reconnects within ~2s while a genuinely-departed one never does.
    A reconnect observed inside the relay delay must cancel the pending relay — otherwise every
    dropout yanks the peer (and then the departed device itself) to the other machine."""

    def test_reconnect_within_the_debounce_window_cancels_the_relay(self, registry, topics):
        subscriber = _make_subscriber(registry, topics, PEER_HOST_INDEX_BY_ROLE, delay=0.2)
        registry.register(KEYBOARD_WPID, _make_keyboard())
        registry.register(MOUSE_WPID, _make_mouse())
        _connect(subscriber, slot=KEYBOARD_SLOT, wpid=KEYBOARD_WPID)
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event())
        _connect(subscriber, slot=KEYBOARD_SLOT, wpid=KEYBOARD_WPID)

        _assert_never_publishes(topics, grace=0.4)

    def test_dropout_followed_by_genuine_departure_still_relays(self, registry, topics):
        """The cancel must consume only the dropout's own pending relay — a later real departure
        (no reconnect inside its window) gets a fresh generation snapshot and must still fire."""
        subscriber = _make_subscriber(registry, topics, PEER_HOST_INDEX_BY_ROLE, delay=0.05)
        registry.register(KEYBOARD_WPID, _make_keyboard())
        registry.register(MOUSE_WPID, _make_mouse())
        _connect(subscriber, slot=KEYBOARD_SLOT, wpid=KEYBOARD_WPID)
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event())
        _connect(subscriber, slot=KEYBOARD_SLOT, wpid=KEYBOARD_WPID)
        subscriber.notify(_make_event())

        _wait_for_publish(topics)
        topics.hid_event.publish.assert_called_once()
        assert topics.hid_event.publish.call_args[0][0].target_host == MOUSE_PEER_INDEX

    def test_peer_reconnect_does_not_cancel_the_departed_devices_relay(self, registry, topics):
        """The generation counter is per-wpid — only a reconnect of the departed device itself
        proves the disconnect was a dropout."""
        subscriber = _make_subscriber(registry, topics, PEER_HOST_INDEX_BY_ROLE, delay=0.05)
        registry.register(KEYBOARD_WPID, _make_keyboard())
        registry.register(MOUSE_WPID, _make_mouse())
        _connect(subscriber, slot=KEYBOARD_SLOT, wpid=KEYBOARD_WPID)
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event())
        _connect(subscriber, slot=MOUSE_SLOT, wpid=MOUSE_WPID)

        _wait_for_publish(topics)
        topics.hid_event.publish.assert_called_once()

    def test_announcement_arriving_during_the_debounce_window_suppresses_the_relay(self, registry, topics):
        """With the relay deferred well past ANNOUNCED_SWITCH_WINDOW_S, the suppression check is
        anchored to the disconnect timestamp — a late x1814 announcement landing after the
        disconnect but before the timer fires must still win."""
        subscriber = _make_subscriber(registry, topics, PEER_HOST_INDEX_BY_ROLE, delay=0.2)
        registry.register(KEYBOARD_WPID, _make_keyboard())
        registry.register(MOUSE_WPID, _make_mouse())
        _connect(subscriber, slot=KEYBOARD_SLOT, wpid=KEYBOARD_WPID)
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event())
        subscriber.notify(HostChangeEvent(slot=KEYBOARD_SLOT, pid=PID, target_host=0))

        _assert_never_publishes(topics, grace=0.4)

    def test_stale_announcement_long_before_the_disconnect_does_not_suppress(self, registry, topics, mocker):
        """Anchoring to the disconnect timestamp must not widen suppression backwards: an
        announcement older than ANNOUNCED_SWITCH_WINDOW_S at disconnect time is unrelated."""
        mocker.patch("cleverswitch.subscriber.peer_host_follow_subscriber.ANNOUNCED_SWITCH_WINDOW_S", 0.05)
        subscriber = _make_subscriber(registry, topics, PEER_HOST_INDEX_BY_ROLE, delay=0.05)
        registry.register(KEYBOARD_WPID, _make_keyboard())
        registry.register(MOUSE_WPID, _make_mouse())
        _connect(subscriber, slot=KEYBOARD_SLOT, wpid=KEYBOARD_WPID)
        subscriber.notify(HostChangeEvent(slot=KEYBOARD_SLOT, pid=PID, target_host=0))
        topics.hid_event.publish.reset_mock()
        time.sleep(0.06)

        subscriber.notify(_make_event())

        _wait_for_publish(topics)
        topics.hid_event.publish.assert_called_once()
