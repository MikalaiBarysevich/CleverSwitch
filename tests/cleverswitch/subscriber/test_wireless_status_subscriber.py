"""Tests for WirelessStatusSubscriber — re-diverts on x1D4B reconfiguration requests."""

from unittest.mock import MagicMock

import pytest

from cleverswitch.event.divert_event import DivertEvent
from cleverswitch.event.hidpp_notification_event import HidppNotificationEvent
from cleverswitch.hidpp.constants import (
    BOLT_PID,
    FEATURE_CHANGE_HOST,
    FEATURE_REPROG_CONTROLS_V4,
)
from cleverswitch.model.logi_device import LogiDevice
from cleverswitch.registry.logi_device_registry import LogiDeviceRegistry
from cleverswitch.subscriber.wireless_status_subscriber import WirelessStatusSubscriber
from cleverswitch.topic.topics import Topics

SLOT = 1
PID = BOLT_PID
WPID = 0x407B
UNKNOWN_FEAT_IDX = 4  # feature index not in available_features.values()
REPROG_IDX = 8
CHANGE_HOST_IDX = 9
DIVERTABLE_CIDS = {0x00D1, 0x00D2, 0x00D3}


def _make_device(
    *,
    reprog_idx: int | None = REPROG_IDX,
    divertable_cids: set[int] | None = None,
) -> LogiDevice:
    features: dict[int, int] = {}
    if reprog_idx is not None:
        features[FEATURE_REPROG_CONTROLS_V4] = reprog_idx
    features[FEATURE_CHANGE_HOST] = CHANGE_HOST_IDX
    return LogiDevice(
        wpid=WPID,
        pid=PID,
        slot=SLOT,
        role="keyboard",
        available_features=features,
        divertable_cids=divertable_cids if divertable_cids is not None else DIVERTABLE_CIDS.copy(),
    )


def _make_x1d4b_event(
    *,
    feature_index: int = UNKNOWN_FEAT_IDX,
    function: int = 0,
    status: int = 0x01,
    request: int = 0x01,
    reason: int = 0x00,
) -> HidppNotificationEvent:
    payload = bytes([status, request, reason]) + b"\x00" * 13
    return HidppNotificationEvent(slot=SLOT, pid=PID, feature_index=feature_index, function=function, payload=payload)


@pytest.fixture
def registry() -> LogiDeviceRegistry:
    return LogiDeviceRegistry()


@pytest.fixture
def divert_topic() -> MagicMock:
    return MagicMock()


@pytest.fixture
def subscriber(registry, divert_topic) -> WirelessStatusSubscriber:
    event_topic = MagicMock()
    topics = Topics(
        hid_event=event_topic,
        write=MagicMock(),
        device_info=MagicMock(),
        divert=divert_topic,
        info_progress=MagicMock(),
    )
    return WirelessStatusSubscriber(registry, topics)


class TestWirelessStatusSubscriber:

    def test_reconfig_request_publishes_divert(self, subscriber, registry, divert_topic):
        registry.register(WPID, _make_device())
        subscriber.notify(_make_x1d4b_event())

        divert_topic.publish.assert_called_once()
        event = divert_topic.publish.call_args[0][0]
        assert isinstance(event, DivertEvent)
        assert event.slot == SLOT
        assert event.pid == PID
        assert event.wpid == WPID
        assert event.cids == DIVERTABLE_CIDS

    def test_no_reconfig_request_ignored(self, subscriber, registry, divert_topic):
        registry.register(WPID, _make_device())
        subscriber.notify(_make_x1d4b_event(request=0x00))

        divert_topic.publish.assert_not_called()

    def test_unknown_device_ignored(self, subscriber, divert_topic):
        subscriber.notify(_make_x1d4b_event())

        divert_topic.publish.assert_not_called()

    def test_no_divertable_cids_ignored(self, subscriber, registry, divert_topic):
        registry.register(WPID, _make_device(divertable_cids=set()))
        subscriber.notify(_make_x1d4b_event())

        divert_topic.publish.assert_not_called()

    def test_known_feature_index_ignored(self, subscriber, registry, divert_topic):
        """Notification from a known feature (e.g. REPROG) should not trigger re-divert."""
        registry.register(WPID, _make_device())
        subscriber.notify(_make_x1d4b_event(feature_index=REPROG_IDX))

        divert_topic.publish.assert_not_called()

    def test_non_event0_function_ignored(self, subscriber, registry, divert_topic):
        registry.register(WPID, _make_device())
        subscriber.notify(_make_x1d4b_event(function=1))

        divert_topic.publish.assert_not_called()

    def test_no_reprog_feature_ignored(self, subscriber, registry, divert_topic):
        registry.register(WPID, _make_device(reprog_idx=None))
        subscriber.notify(_make_x1d4b_event())

        divert_topic.publish.assert_not_called()

    def test_non_notification_event_ignored(self, subscriber, registry, divert_topic):
        registry.register(WPID, _make_device())
        subscriber.notify("not a HidppNotificationEvent")

        divert_topic.publish.assert_not_called()

    def test_status_unknown_with_reconfig_request_still_diverts(self, subscriber, registry, divert_topic):
        registry.register(WPID, _make_device())
        subscriber.notify(_make_x1d4b_event(status=0x00, request=0x01))

        divert_topic.publish.assert_called_once()
