"""Unit tests for subscriber/device_info_subscriber.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.cleverswitch.event.device_info_request_event import DeviceInfoRequestEvent
from src.cleverswitch.hidpp.constants import BOLT_PID
from src.cleverswitch.model.logi_device import LogiDevice
from src.cleverswitch.registry.logi_device_registry import LogiDeviceRegistry
from src.cleverswitch.subscriber.device_info_subscriber import DeviceInfoSubscriber
from src.cleverswitch.subscriber.task.constants import Task
from src.cleverswitch.topic.topic import Topic
from src.cleverswitch.topic.topics import Topics

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


def _make_device(role="keyboard"):
    return LogiDevice(wpid=WPID, pid=PID, slot=1, role=role, available_features={})


def test_handle_setup_starts_tasks(mocker):
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DeviceInfoSubscriber(registry, topics)

    device = _make_device()
    registry.register(WPID, device)

    mock_reprog = mocker.patch("src.cleverswitch.subscriber.device_info_subscriber.CidReportingFeatureTask")
    mock_change_host = mocker.patch("src.cleverswitch.subscriber.device_info_subscriber.ChangeHostFeatureTask")
    mock_name_type = mocker.patch("src.cleverswitch.subscriber.device_info_subscriber.NameAndTypeFeatureTask")

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

    mock_reprog = mocker.patch("cleverswitch.subscriber.device_info_subscriber.CidReportingFeatureTask")

    event = DeviceInfoRequestEvent(slot=1, pid=PID, wpid=0x9999, type=True, name=True)
    sub.notify(event)

    mock_reprog.assert_not_called()


def test_handle_setup_discards_type_step_when_not_needed(mocker):
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DeviceInfoSubscriber(registry, topics)

    device = _make_device()
    registry.register(WPID, device)

    mocker.patch("cleverswitch.subscriber.device_info_subscriber.CidReportingFeatureTask")
    mocker.patch("cleverswitch.subscriber.device_info_subscriber.ChangeHostFeatureTask")
    mocker.patch("cleverswitch.subscriber.device_info_subscriber.NameAndTypeFeatureTask")

    event = DeviceInfoRequestEvent(slot=1, pid=PID, wpid=WPID, type=False, name=True)
    sub.notify(event)

    assert Task.Name.GET_DEVICE_TYPE not in device.pending_steps


def test_handle_setup_discards_name_step_when_not_needed(mocker):
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DeviceInfoSubscriber(registry, topics)

    device = _make_device()
    registry.register(WPID, device)

    mocker.patch("cleverswitch.subscriber.device_info_subscriber.CidReportingFeatureTask")
    mocker.patch("cleverswitch.subscriber.device_info_subscriber.ChangeHostFeatureTask")
    mocker.patch("cleverswitch.subscriber.device_info_subscriber.NameAndTypeFeatureTask")

    event = DeviceInfoRequestEvent(slot=1, pid=PID, wpid=WPID, type=True, name=False)
    sub.notify(event)

    assert Task.Name.GET_DEVICE_NAME not in device.pending_steps


def test_non_device_info_event_ignored():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = DeviceInfoSubscriber(registry, topics)
    sub.notify("not an event")  # must not raise
