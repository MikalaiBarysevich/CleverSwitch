"""Unit tests for subscriber/task/feature/ — FeatureTask and subclasses."""

from __future__ import annotations

from unittest.mock import MagicMock

from cleverswitch.model.logi_device import ROLE_KEYBOARD, ROLE_MOUSE
from src.cleverswitch.event.hidpp_error_event import HidppErrorEvent
from src.cleverswitch.event.hidpp_response_event import HidppResponseEvent
from src.cleverswitch.hidpp.constants import (
    BOLT_PID,
    FEATURE_CHANGE_HOST,
    FEATURE_DEVICE_FRIENDLY_NAME,
    FEATURE_DEVICE_TYPE_AND_NAME,
    FEATURE_REPROG_CONTROLS_V4,
)
from src.cleverswitch.model.logi_device import LogiDevice
from src.cleverswitch.subscriber.task.constants import (
    FEATURE_CHANGE_HOST_SW_ID,
    FEATURE_DEVICE_FRIENDLY_NAME_SW_ID,
    FEATURE_DEVICE_TYPE_AND_NAME_SW_ID,
    FEATURE_REPROG_CONTROLS_V4_SW_ID,
    Task,
)
from src.cleverswitch.subscriber.task.feature.change_host_feature_task import ChangeHostFeatureTask
from src.cleverswitch.subscriber.task.feature.cid_reporting_feature_task import CidReportingFeatureTask
from src.cleverswitch.subscriber.task.feature.friendly_name_feature_task import FriendlyNameFeatureTask
from src.cleverswitch.subscriber.task.feature.name_and_type_feature_task import NameAndTypeFeatureTask
from src.cleverswitch.topic.topic import Topic
from src.cleverswitch.topic.topics import Topics
from tests.task_helpers import deliver_on_request

PID = BOLT_PID
SLOT = 1


def _make_device(pending=None, features=None):
    d = LogiDevice(wpid=0x407B, pid=PID, slot=SLOT, role=ROLE_KEYBOARD, available_features=features or {})
    if pending is not None:
        d.pending_steps = set(pending)
    return d


def _make_topics():
    return Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        flags=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
    )


def _response(sw_id, feat_idx):
    """Build a fake HidppResponseEvent with feat_idx in payload[0]."""
    payload = bytes([feat_idx]) + bytes(15)
    return HidppResponseEvent(slot=SLOT, pid=PID, feature_index=0, function=0, sw_id=sw_id, payload=payload)


# ── ChangeHostFeatureTask ─────────────────────────────────────────────────────


def test_change_host_resolves_feature_index():
    device = _make_device(pending={Task.Feature.Name.CHANGE_HOST})
    topics = _make_topics()
    task = ChangeHostFeatureTask(device, topics)

    # Inject a successful response before doTask blocks
    deliver_on_request(task, topics, [_response(FEATURE_CHANGE_HOST_SW_ID, 9)])
    task.doTask()

    assert device.available_features.get(FEATURE_CHANGE_HOST) == 9
    assert Task.Feature.Name.CHANGE_HOST not in device.pending_steps


def test_change_host_noop_on_timeout():
    device = _make_device(pending={Task.Feature.Name.CHANGE_HOST})
    topics = _make_topics()
    task = ChangeHostFeatureTask(device, topics)

    # Monkey-patch wait to return None immediately
    task._wait_response = lambda timeout=2.0: None
    task.doTask()

    assert FEATURE_CHANGE_HOST not in device.available_features
    assert Task.Feature.Name.CHANGE_HOST in device.pending_steps


def test_change_host_noop_on_error_response():
    device = _make_device(pending={Task.Feature.Name.CHANGE_HOST})
    topics = _make_topics()
    task = ChangeHostFeatureTask(device, topics)

    deliver_on_request(
        task,
        topics,
        [
            HidppErrorEvent(
                slot=SLOT, pid=PID, feature_index=0, function=0, sw_id=FEATURE_CHANGE_HOST_SW_ID, error_code=5
            ),
        ],
    )
    task.doTask()

    assert FEATURE_CHANGE_HOST not in device.available_features


def test_change_host_noop_when_feat_idx_is_zero():
    device = _make_device(pending={Task.Feature.Name.CHANGE_HOST})
    topics = _make_topics()
    task = ChangeHostFeatureTask(device, topics)

    deliver_on_request(task, topics, [_response(FEATURE_CHANGE_HOST_SW_ID, 0)])
    task.doTask()

    assert FEATURE_CHANGE_HOST not in device.available_features


def test_skips_request_when_feature_code_already_resolved():
    device = _make_device(pending={Task.Feature.Name.CHANGE_HOST}, features={FEATURE_CHANGE_HOST: 9})
    topics = _make_topics()
    task = ChangeHostFeatureTask(device, topics)

    task.doTask()

    topics.write.publish.assert_not_called()
    assert Task.Feature.Name.CHANGE_HOST not in device.pending_steps


def test_index_equal_to_feature_code_does_not_count_as_resolved():
    device = _make_device(
        pending={Task.Feature.Name.NAME_AND_TYPE},
        features={FEATURE_CHANGE_HOST: FEATURE_DEVICE_TYPE_AND_NAME},
    )
    topics = _make_topics()
    task = NameAndTypeFeatureTask(device, topics)
    task._wait_response = lambda timeout=2.0: None

    task.doTask()

    topics.write.publish.assert_called_once()
    assert Task.Feature.Name.NAME_AND_TYPE in device.pending_steps


def test_already_resolved_feature_fires_dependents_once(mocker):
    device = _make_device(pending={Task.Feature.Name.CID_REPORTING}, features={FEATURE_REPROG_CONTROLS_V4: 8})
    topics = _make_topics()
    task = CidReportingFeatureTask(device, topics)
    mock_find = mocker.patch("src.cleverswitch.subscriber.task.feature.cid_reporting_feature_task.FindESCidsFlagsTask")

    task.run()

    mock_find.return_value.start.assert_called_once()


# ── CidReportingFeatureTask ───────────────────────────────────────────────────


def test_reprog_resolves_feature_index():
    device = _make_device(pending={Task.Feature.Name.CID_REPORTING})
    topics = _make_topics()
    task = CidReportingFeatureTask(device, topics)

    deliver_on_request(task, topics, [_response(FEATURE_REPROG_CONTROLS_V4_SW_ID, 8)])
    task.doTask()

    assert device.available_features.get(FEATURE_REPROG_CONTROLS_V4) == 8
    assert Task.Feature.Name.CID_REPORTING not in device.pending_steps


def test_reprog_keeps_step_pending_when_keyboard_reports_unsupported():
    device = _make_device(pending={Task.Feature.Name.CID_REPORTING})
    topics = _make_topics()
    task = CidReportingFeatureTask(device, topics)

    deliver_on_request(task, topics, [_response(FEATURE_REPROG_CONTROLS_V4_SW_ID, 0)])
    task.doTask()

    assert FEATURE_REPROG_CONTROLS_V4 not in device.available_features
    assert Task.Feature.Name.CID_REPORTING in device.pending_steps


def test_reprog_accepts_unsupported_for_non_keyboard():
    device = _make_device(pending={Task.Feature.Name.CID_REPORTING})
    device.role = ROLE_MOUSE
    topics = _make_topics()
    task = CidReportingFeatureTask(device, topics)

    deliver_on_request(task, topics, [_response(FEATURE_REPROG_CONTROLS_V4_SW_ID, 0)])
    task.doTask()

    assert Task.Feature.Name.CID_REPORTING not in device.pending_steps


def test_reprog_fires_dependent_steps(mocker):
    device = _make_device(pending={Task.Feature.Name.CID_REPORTING})
    topics = _make_topics()
    task = CidReportingFeatureTask(device, topics)

    mock_find = mocker.patch("src.cleverswitch.subscriber.task.feature.cid_reporting_feature_task.FindESCidsFlagsTask")
    task._fire_dependent_steps()

    mock_find.assert_called_once_with(device, topics)
    mock_find.return_value.start.assert_called_once()


# ── NameAndTypeFeatureTask ────────────────────────────────────────────────────


def test_name_and_type_resolves_feature_index():
    device = _make_device(pending={Task.Feature.Name.NAME_AND_TYPE})
    topics = _make_topics()
    task = NameAndTypeFeatureTask(device, topics)

    deliver_on_request(task, topics, [_response(FEATURE_DEVICE_TYPE_AND_NAME_SW_ID, 5)])
    task.doTask()

    assert device.available_features.get(FEATURE_DEVICE_TYPE_AND_NAME) == 5
    assert Task.Feature.Name.NAME_AND_TYPE not in device.pending_steps


def test_name_and_type_fires_dependent_steps(mocker):
    device = _make_device(pending={Task.Feature.Name.NAME_AND_TYPE})
    topics = _make_topics()
    task = NameAndTypeFeatureTask(device, topics)

    mock_type = mocker.patch("src.cleverswitch.subscriber.task.feature.name_and_type_feature_task.GetDeviceTypeTask")
    mock_name = mocker.patch("src.cleverswitch.subscriber.task.feature.name_and_type_feature_task.GetDeviceNameTask")
    task._fire_dependent_steps()

    mock_type.assert_called_once_with(device, topics)
    mock_type.return_value.start.assert_called_once()
    mock_name.assert_called_once_with(device, topics)
    mock_name.return_value.start.assert_called_once()


# ── FriendlyNameFeatureTask ───────────────────────────────────────────────────


def test_friendly_name_resolves_feature_index():
    device = _make_device(pending={Task.Feature.Name.FRIENDLY_NAME})
    topics = _make_topics()
    task = FriendlyNameFeatureTask(device, topics)

    deliver_on_request(task, topics, [_response(FEATURE_DEVICE_FRIENDLY_NAME_SW_ID, 3)])
    task.doTask()

    assert device.available_features.get(FEATURE_DEVICE_FRIENDLY_NAME) == 3
    assert Task.Feature.Name.FRIENDLY_NAME not in device.pending_steps


def test_friendly_name_fires_dependent_steps(mocker):
    device = _make_device(pending={Task.Feature.Name.FRIENDLY_NAME})
    topics = _make_topics()
    task = FriendlyNameFeatureTask(device, topics)

    mock_get = mocker.patch(
        "src.cleverswitch.subscriber.task.feature.friendly_name_feature_task.GetDeviceFriendlyNameTask"
    )
    task._fire_dependent_steps()

    mock_get.assert_called_once_with(device, topics)
    mock_get.return_value.start.assert_called_once()
