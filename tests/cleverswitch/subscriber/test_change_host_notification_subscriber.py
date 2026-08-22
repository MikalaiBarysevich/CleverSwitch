"""Tests for ChangeHostNotificationSubscriber — turns x1814 announcements into HostChangeEvents."""

from unittest.mock import MagicMock

import pytest

from cleverswitch.event.hidpp_notification_event import HidppNotificationEvent
from cleverswitch.event.host_change_event import HostChangeEvent
from cleverswitch.hidpp.constants import (
    BOLT_PID,
    FEATURE_CHANGE_HOST,
    FEATURE_REPROG_CONTROLS_V4,
)
from cleverswitch.model.logi_device import LogiDevice
from cleverswitch.registry.logi_device_registry import LogiDeviceRegistry
from cleverswitch.subscriber.change_host_notification_subscriber import ChangeHostNotificationSubscriber
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics

SLOT = 2
PID = BOLT_PID
WPID = 0xB378
REPROG_IDX = 9
CHANGE_HOST_IDX = 10


def _make_device(*, slot: int = SLOT, pid: int = PID, change_host_idx: int | None = CHANGE_HOST_IDX) -> LogiDevice:
    features = {FEATURE_REPROG_CONTROLS_V4: REPROG_IDX}
    if change_host_idx is not None:
        features[FEATURE_CHANGE_HOST] = change_host_idx
    return LogiDevice(
        wpid=WPID,
        pid=pid,
        slot=slot,
        role="keyboard",
        available_features=features,
        friendly_name="MX KEYS S",
    )


def _make_event(
    *,
    slot: int = SLOT,
    pid: int = PID,
    feature_index: int = CHANGE_HOST_IDX,
    function: int = 0,
    payload: bytes = b"\x00\x01",
) -> HidppNotificationEvent:
    return HidppNotificationEvent(
        slot=slot,
        pid=pid,
        feature_index=feature_index,
        function=function,
        payload=payload + b"\x00" * (16 - len(payload)),
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
def subscriber(registry, topics) -> ChangeHostNotificationSubscriber:
    return ChangeHostNotificationSubscriber(registry, topics)


class TestChangeHostNotificationSubscriber:
    def test_announcement_publishes_host_change_event(self, subscriber, registry, topics):
        registry.register(WPID, _make_device())
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event(payload=b"\x00\x01"))

        topics.hid_event.publish.assert_called_once()
        event = topics.hid_event.publish.call_args[0][0]
        assert isinstance(event, HostChangeEvent)
        assert event.target_host == 1
        assert event.slot == SLOT
        assert event.pid == PID

    def test_reverse_direction_reads_second_payload_byte(self, subscriber, registry, topics):
        """macOS capture: on host 2, pressed host 1 — payload[0] is the departing host, not the target."""
        registry.register(WPID, _make_device())
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event(payload=b"\x01\x00"))

        event = topics.hid_event.publish.call_args[0][0]
        assert event.target_host == 0

    def test_third_host_accepted(self, subscriber, registry, topics):
        registry.register(WPID, _make_device())
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event(payload=b"\x00\x02"))

        event = topics.hid_event.publish.call_args[0][0]
        assert event.target_host == 2

    def test_other_feature_index_ignored(self, subscriber, registry, topics):
        """An x1D4B reconfiguration event decodes to the same bytes — only the index tells them apart."""
        registry.register(WPID, _make_device())
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event(feature_index=4, payload=b"\x00\x01"))

        topics.hid_event.publish.assert_not_called()

    def test_reprog_feature_index_ignored(self, subscriber, registry, topics):
        registry.register(WPID, _make_device())
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event(feature_index=REPROG_IDX))

        topics.hid_event.publish.assert_not_called()

    def test_device_without_change_host_feature_ignored(self, subscriber, registry, topics):
        registry.register(WPID, _make_device(change_host_idx=None))
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event())

        topics.hid_event.publish.assert_not_called()

    def test_unknown_device_ignored(self, subscriber, topics):
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event())

        topics.hid_event.publish.assert_not_called()

    def test_other_slot_on_same_receiver_ignored(self, subscriber, registry, topics):
        """Receiver-paired devices share a pid — only the slot disambiguates them."""
        registry.register(WPID, _make_device(slot=3))
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event(slot=SLOT))

        topics.hid_event.publish.assert_not_called()

    def test_other_pid_ignored(self, subscriber, registry, topics):
        registry.register(WPID, _make_device(pid=0xC52B))
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event(pid=PID))

        topics.hid_event.publish.assert_not_called()

    def test_non_zero_function_ignored(self, subscriber, registry, topics):
        """fn=1 is the setCurrentHost echo, not an announcement."""
        registry.register(WPID, _make_device())
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event(function=1))

        topics.hid_event.publish.assert_not_called()

    def test_short_payload_ignored(self, subscriber, registry, topics):
        registry.register(WPID, _make_device())
        topics.hid_event.publish.reset_mock()

        subscriber.notify(
            HidppNotificationEvent(slot=SLOT, pid=PID, feature_index=CHANGE_HOST_IDX, function=0, payload=b"\x00")
        )

        topics.hid_event.publish.assert_not_called()

    def test_out_of_range_target_host_ignored(self, subscriber, registry, topics):
        """A getHostInfo reply leaking through would carry nbHost here — never a valid host index."""
        registry.register(WPID, _make_device())
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event(payload=b"\x03\x03"))

        topics.hid_event.publish.assert_not_called()

    def test_non_notification_event_ignored(self, subscriber, registry, topics):
        registry.register(WPID, _make_device())
        topics.hid_event.publish.reset_mock()

        subscriber.notify("not a HidppNotificationEvent")

        topics.hid_event.publish.assert_not_called()

    def test_subscribes_to_hid_event_topic(self, registry, topics):
        subscriber = ChangeHostNotificationSubscriber(registry, topics)

        topics.hid_event.subscribe.assert_called_once_with(subscriber)
