"""Unit tests for subscriber/device_info_subscriber.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from cleverswitch.event.device_info_request_event import DeviceInfoRequestEvent
from cleverswitch.hidpp.constants import BOLT_PID
from cleverswitch.model.logi_device import LogiDevice
from cleverswitch.registry.logi_device_registry import LogiDeviceRegistry
from cleverswitch.subscriber.device_info_subscriber import DeviceInfoSubscriber
from cleverswitch.topic.topic import Topic

PID = BOLT_PID
WPID = 0x407B


def _make_topics():
    return {
        "event_topic": MagicMock(spec=Topic),
        "write_topic": MagicMock(spec=Topic),
        "device_info_topic": MagicMock(spec=Topic),
        "divert_topic": MagicMock(spec=Topic),
    }


def _make_device():
    return LogiDevice(wpid=WPID, pid=PID, slot=1, role=None, available_features={})


def test_handle_setup_starts_tasks(mocker):
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DeviceInfoSubscriber(registry, topics)

    device = _make_device()
    registry.register(WPID, device)

    mock_reprog = mocker.patch("cleverswitch.subscriber.device_info_subscriber.ReprogFeatureTask")
    mock_change_host = mocker.patch("cleverswitch.subscriber.device_info_subscriber.ChangeHostFeatureTask")
    mock_name_type = mocker.patch("cleverswitch.subscriber.device_info_subscriber.NameAndTypeFeatureTask")

    event = DeviceInfoRequestEvent(slot=1, pid=PID, wpid=WPID, type=True, name=True)
    sub.notify(event)

    mock_reprog.assert_called_once_with(device, topics)
    mock_reprog.return_value.start.assert_called_once()
    mock_change_host.assert_called_once_with(device, topics)
    mock_change_host.return_value.start.assert_called_once()
    mock_name_type.assert_called_once_with(device, topics)
    mock_name_type.return_value.start.assert_called_once()


def test_handle_setup_skips_when_device_not_found(mocker):
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DeviceInfoSubscriber(registry, topics)

    mock_reprog = mocker.patch("cleverswitch.subscriber.device_info_subscriber.ReprogFeatureTask")

    event = DeviceInfoRequestEvent(slot=1, pid=PID, wpid=0x9999, type=True, name=True)
    sub.notify(event)

    mock_reprog.assert_not_called()


def test_handle_setup_discards_type_step_when_not_needed(mocker):
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DeviceInfoSubscriber(registry, topics)

    device = _make_device()
    registry.register(WPID, device)

    mocker.patch("cleverswitch.subscriber.device_info_subscriber.ReprogFeatureTask")
    mocker.patch("cleverswitch.subscriber.device_info_subscriber.ChangeHostFeatureTask")
    mocker.patch("cleverswitch.subscriber.device_info_subscriber.NameAndTypeFeatureTask")

    event = DeviceInfoRequestEvent(slot=1, pid=PID, wpid=WPID, type=False, name=True)
    sub.notify(event)

    assert "get_device_type" not in device.pending_steps


def test_handle_setup_discards_name_step_when_not_needed(mocker):
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DeviceInfoSubscriber(registry, topics)

    device = _make_device()
    registry.register(WPID, device)

    mocker.patch("cleverswitch.subscriber.device_info_subscriber.ReprogFeatureTask")
    mocker.patch("cleverswitch.subscriber.device_info_subscriber.ChangeHostFeatureTask")
    mocker.patch("cleverswitch.subscriber.device_info_subscriber.NameAndTypeFeatureTask")

    event = DeviceInfoRequestEvent(slot=1, pid=PID, wpid=WPID, type=True, name=False)
    sub.notify(event)

    assert "get_device_name" not in device.pending_steps


def test_non_device_info_event_ignored():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DeviceInfoSubscriber(registry, topics)
    sub.notify("not an event")  # must not raise
