"""Tests for WirelessReconnectSubscriberMac — fires DeviceConnectedEvent on x1D4B."""

from unittest.mock import MagicMock

from cleverswitch.event.device_connected_event import DeviceConnectedEvent
from cleverswitch.event.hidpp_notification_event import HidppNotificationEvent
from cleverswitch.hidpp.constants import BOLT_PID, FEATURE_CHANGE_HOST, FEATURE_REPROG_CONTROLS_V4
from cleverswitch.model.logi_device import LogiDevice
from cleverswitch.registry.logi_device_registry import LogiDeviceRegistry
from cleverswitch.subscriber.wireless_reconnect_subscriber import WirelessReconnectSubscriber
from cleverswitch.topic.topics import Topics

SLOT = 1
PID = BOLT_PID
WPID = 0x407B
UNKNOWN_FEAT_IDX = 4  # feature index not in available_features.values()
REPROG_IDX = 8
CHANGE_HOST_IDX = 9


def _make_device() -> LogiDevice:
    return LogiDevice(
        wpid=WPID,
        pid=PID,
        slot=SLOT,
        role="keyboard",
        available_features={FEATURE_REPROG_CONTROLS_V4: REPROG_IDX, FEATURE_CHANGE_HOST: CHANGE_HOST_IDX},
    )


def _make_x1d4b_event(*, feature_index: int = UNKNOWN_FEAT_IDX, function: int = 0, request: int = 0x01):
    payload = bytes([0x00, request, 0x00]) + b"\x00" * 13
    return HidppNotificationEvent(slot=SLOT, pid=PID, feature_index=feature_index, function=function, payload=payload)


def _make_subscriber(registry):
    event_topic = MagicMock()
    topics = Topics(
        hid_event=event_topic,
        write=MagicMock(),
        device_info=MagicMock(),
        flags=MagicMock(),
        info_progress=MagicMock(),
    )
    sub = WirelessReconnectSubscriber(registry, topics)
    return sub, event_topic


def test_publishes_reconnect_on_x1d4b():
    registry = LogiDeviceRegistry()
    registry.register(WPID, _make_device())
    sub, event_topic = _make_subscriber(registry)

    sub.notify(_make_x1d4b_event())

    event_topic.publish.assert_called_once()
    published = event_topic.publish.call_args[0][0]
    assert isinstance(published, DeviceConnectedEvent)
    assert published.link_established is True
    assert published.slot == SLOT
    assert published.pid == PID
    assert published.wpid == WPID


def test_ignores_known_feature_index():
    registry = LogiDeviceRegistry()
    registry.register(WPID, _make_device())
    sub, event_topic = _make_subscriber(registry)

    sub.notify(_make_x1d4b_event(feature_index=REPROG_IDX))

    event_topic.publish.assert_not_called()


def test_ignores_wrong_payload():
    registry = LogiDeviceRegistry()
    registry.register(WPID, _make_device())
    sub, event_topic = _make_subscriber(registry)

    sub.notify(_make_x1d4b_event(request=0x00))

    event_topic.publish.assert_not_called()


def test_ignores_unknown_device():
    registry = LogiDeviceRegistry()
    sub, event_topic = _make_subscriber(registry)

    sub.notify(_make_x1d4b_event())

    event_topic.publish.assert_not_called()


def test_ignores_non_zero_function():
    registry = LogiDeviceRegistry()
    registry.register(WPID, _make_device())
    sub, event_topic = _make_subscriber(registry)

    sub.notify(_make_x1d4b_event(function=1))

    event_topic.publish.assert_not_called()
