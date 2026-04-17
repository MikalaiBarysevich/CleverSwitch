"""Tests for DisconnectPollerSubscriber — ping-based disconnect detection."""

import time
from unittest.mock import MagicMock, patch

import pytest

from cleverswitch.event.device_connected_event import DeviceConnectedEvent
from cleverswitch.event.hidpp_response_event import HidppResponseEvent
from cleverswitch.event.write_event import WriteEvent
from cleverswitch.hidpp.constants import BOLT_PID, SW_ID
from cleverswitch.model.logi_device import LogiDevice
from cleverswitch.registry.logi_device_registry import LogiDeviceRegistry
from cleverswitch.subscriber.disconnect_poller_subscriber import DisconnectPollerSubscriber
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics

WPID = 0x407B
SLOT = 1


def _make_device(slot: int = SLOT, wpid: int = WPID) -> LogiDevice:
    return LogiDevice(
        wpid=wpid,
        pid=BOLT_PID,
        slot=slot,
        role="keyboard",
        available_features={},
    )


def _make_ping_response(slot: int = SLOT) -> HidppResponseEvent:
    return HidppResponseEvent(
        slot=slot,
        pid=BOLT_PID,
        feature_index=0,
        function=1,
        sw_id=SW_ID,
        payload=bytes(16),
    )


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
def subscriber(registry, topics) -> DisconnectPollerSubscriber:
    with patch.object(DisconnectPollerSubscriber, "__init__", lambda self, *a, **kw: None):
        sub = DisconnectPollerSubscriber.__new__(DisconnectPollerSubscriber)
        sub._device_registry = registry
        sub._topics = topics
        sub._last_seen = {}
        sub._connected = {}
    return sub


class TestDisconnectPollerSubscriber:

    def test_ping_response_updates_last_seen(self, subscriber):
        subscriber.notify(_make_ping_response())
        assert SLOT in subscriber._last_seen
        assert subscriber._connected[SLOT] is True

    def test_non_matching_response_ignored(self, subscriber):
        event = HidppResponseEvent(slot=SLOT, pid=BOLT_PID, feature_index=5, function=1, sw_id=SW_ID, payload=bytes(16))
        subscriber.notify(event)
        assert SLOT not in subscriber._last_seen

    def test_wrong_sw_id_ignored(self, subscriber):
        event = HidppResponseEvent(slot=SLOT, pid=BOLT_PID, feature_index=0, function=1, sw_id=0x0E, payload=bytes(16))
        subscriber.notify(event)
        assert SLOT not in subscriber._last_seen

    def test_poll_sends_ping_for_registered_device(self, subscriber, registry, topics):
        registry.register(WPID, _make_device())
        subscriber._poll_loop_once()
        topics.write.publish.assert_called_once()
        event = topics.write.publish.call_args[0][0]
        assert isinstance(event, WriteEvent)
        assert event.hid_message[1] == SLOT
        assert event.hid_message[2] == 0x00  # feature index 0

    def test_poll_skips_bt_device(self, subscriber, registry, topics):
        registry.register(WPID, _make_device(slot=0xFF))
        subscriber._poll_loop_once()
        topics.write.publish.assert_not_called()

    def test_timeout_publishes_disconnect(self, subscriber, registry, topics):
        registry.register(WPID, _make_device())
        subscriber._last_seen[SLOT] = time.monotonic() - 2.0
        subscriber._connected[SLOT] = True
        subscriber._check_timeouts()
        topics.hid_event.publish.assert_called_once()
        event = topics.hid_event.publish.call_args[0][0]
        assert isinstance(event, DeviceConnectedEvent)
        assert event.link_established is False
        assert event.wpid == WPID
        assert event.slot == SLOT

    def test_timeout_fires_only_once(self, subscriber, registry, topics):
        registry.register(WPID, _make_device())
        subscriber._last_seen[SLOT] = time.monotonic() - 2.0
        subscriber._connected[SLOT] = True
        subscriber._check_timeouts()
        subscriber._check_timeouts()
        assert topics.hid_event.publish.call_count == 1

    def test_reconnect_after_disconnect_resets_state(self, subscriber, registry, topics):
        registry.register(WPID, _make_device())
        subscriber._last_seen[SLOT] = time.monotonic() - 2.0
        subscriber._connected[SLOT] = True
        subscriber._check_timeouts()
        assert subscriber._connected[SLOT] is False

        subscriber.notify(_make_ping_response())
        assert subscriber._connected[SLOT] is True
