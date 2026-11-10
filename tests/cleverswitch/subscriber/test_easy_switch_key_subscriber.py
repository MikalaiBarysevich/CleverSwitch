"""Tests for EasySwitchKeySubscriber — turns x1B04 Easy-Switch presses into HostChangeEvents."""

from unittest.mock import MagicMock

import pytest

from cleverswitch.event.hidpp_notification_event import HidppNotificationEvent
from cleverswitch.event.host_change_event import HostChangeEvent
from cleverswitch.hidpp.constants import (
    BOLT_PID,
    FEATURE_CHANGE_HOST,
    FEATURE_REPROG_CONTROLS_V4,
)
from cleverswitch.model.logi_device import ROLE_KEYBOARD, LogiDevice
from cleverswitch.registry.logi_device_registry import LogiDeviceRegistry
from cleverswitch.subscriber.easy_switch_key_subscriber import EasySwitchKeySubscriber
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics

SLOT = 2
PID = BOLT_PID
WPID = 0xB378
REPROG_IDX = 9
CHANGE_HOST_IDX = 10


def _make_device(*, slot: int = SLOT, pid: int = PID, reprog_idx: int | None = REPROG_IDX) -> LogiDevice:
    features = {FEATURE_CHANGE_HOST: CHANGE_HOST_IDX}
    if reprog_idx is not None:
        features[FEATURE_REPROG_CONTROLS_V4] = reprog_idx
    return LogiDevice(
        wpid=WPID,
        pid=pid,
        slot=slot,
        role=ROLE_KEYBOARD,
        available_features=features,
        friendly_name="MX Keys",
    )


def _make_event(
    *,
    slot: int = SLOT,
    pid: int = PID,
    feature_index: int = REPROG_IDX,
    function: int = 0,
    payload: bytes = b"\x00\xd1",
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
def subscriber(registry, topics) -> EasySwitchKeySubscriber:
    return EasySwitchKeySubscriber(registry, topics)


class TestEasySwitchKeySubscriber:
    def test_diverted_press_from_reprog_feature_publishes_host_change(self, subscriber, registry, topics):
        registry.register(WPID, _make_device())
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event(function=0, payload=b"\x00\xd2"))

        topics.hid_event.publish.assert_called_once()
        event = topics.hid_event.publish.call_args[0][0]
        assert isinstance(event, HostChangeEvent)
        assert event.target_host == 1
        assert event.slot == SLOT
        assert event.pid == PID

    def test_analytics_press_publishes_host_change(self, subscriber, registry, topics):
        registry.register(WPID, _make_device())
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event(function=2, payload=b"\x00\xd3\x01"))

        topics.hid_event.publish.assert_called_once()
        event = topics.hid_event.publish.call_args[0][0]
        assert isinstance(event, HostChangeEvent)
        assert event.target_host == 2

    def test_analytics_release_is_ignored(self, subscriber, registry, topics):
        registry.register(WPID, _make_device())
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event(function=2, payload=b"\x00\xd3\x00"))

        topics.hid_event.publish.assert_not_called()

    def test_same_bytes_from_another_feature_are_ignored(self, subscriber, registry, topics):
        """The bug: another feature's notification with the same leading bytes must not switch hosts."""
        registry.register(WPID, _make_device())
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event(feature_index=CHANGE_HOST_IDX, function=0, payload=b"\x00\xd1"))

        topics.hid_event.publish.assert_not_called()

    def test_device_without_reprog_feature_is_ignored(self, subscriber, registry, topics):
        registry.register(WPID, _make_device(reprog_idx=None))
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event())

        topics.hid_event.publish.assert_not_called()

    def test_unknown_device_is_ignored(self, subscriber, topics):
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event())

        topics.hid_event.publish.assert_not_called()

    def test_non_es_cid_is_ignored(self, subscriber, registry, topics):
        registry.register(WPID, _make_device())
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event(payload=b"\x00\xaa"))

        topics.hid_event.publish.assert_not_called()

    def test_other_function_is_ignored(self, subscriber, registry, topics):
        registry.register(WPID, _make_device())
        topics.hid_event.publish.reset_mock()

        subscriber.notify(_make_event(function=1, payload=b"\x00\xd1"))

        topics.hid_event.publish.assert_not_called()

    def test_short_payload_is_ignored(self, subscriber, registry, topics):
        registry.register(WPID, _make_device())
        topics.hid_event.publish.reset_mock()

        subscriber.notify(
            HidppNotificationEvent(slot=SLOT, pid=PID, feature_index=REPROG_IDX, function=0, payload=b"\x00\xd1")
        )

        topics.hid_event.publish.assert_not_called()

    def test_subscribes_to_hid_event_topic(self, registry, topics):
        subscriber = EasySwitchKeySubscriber(registry, topics)

        topics.hid_event.subscribe.assert_called_once_with(subscriber)
