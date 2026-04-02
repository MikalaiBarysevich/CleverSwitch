"""Unit tests for subscriber/task/feature/ — FeatureTask and subclasses."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from cleverswitch.event.hidpp_error_event import HidppErrorEvent
from cleverswitch.event.hidpp_response_event import HidppResponseEvent
from cleverswitch.hidpp.constants import BOLT_PID, FEATURE_CHANGE_HOST, FEATURE_DEVICE_TYPE_AND_NAME, FEATURE_REPROG_CONTROLS_V4
from cleverswitch.model.logi_device import LogiDevice
from cleverswitch.subscriber.task.constants import (
    FEATURE_CHANGE_HOST_SW_ID,
    FEATURE_DEVICE_TYPE_AND_NAME_SW_ID,
    FEATURE_REPROG_CONTROLS_V4_SW_ID,
)
from cleverswitch.subscriber.task.feature.change_host_feature_task import ChangeHostFeatureTask
from cleverswitch.subscriber.task.feature.name_and_type_feature_task import NameAndTypeFeatureTask
from cleverswitch.subscriber.task.feature.reprog_feature_task import ReprogFeatureTask
from cleverswitch.topic.topic import Topic

PID = BOLT_PID
SLOT = 1


def _make_device(pending=None, features=None):
    d = LogiDevice(wpid=0x407B, pid=PID, slot=SLOT, role="keyboard", available_features=features or {})
    if pending is not None:
        d.pending_steps = set(pending)
    return d


def _make_topics():
    return {
        "event_topic": MagicMock(spec=Topic),
        "write_topic": MagicMock(spec=Topic),
        "device_info_topic": MagicMock(spec=Topic),
        "divert_topic": MagicMock(spec=Topic),
    }


def _response(sw_id, feat_idx):
    """Build a fake HidppResponseEvent with feat_idx in payload[0]."""
    payload = bytes([feat_idx]) + bytes(15)
    return HidppResponseEvent(slot=SLOT, pid=PID, feature_index=0, function=0, sw_id=sw_id, payload=payload)


# ── ChangeHostFeatureTask ─────────────────────────────────────────────────────


def test_change_host_resolves_feature_index():
    device = _make_device(pending={"resolve_change_host"})
    topics = _make_topics()
    task = ChangeHostFeatureTask(device, topics)

    # Inject a successful response before doTask blocks
    task._response_queue.put(_response(FEATURE_CHANGE_HOST_SW_ID, 9))
    task.doTask()

    assert device.available_features.get(FEATURE_CHANGE_HOST) == 9
    assert "resolve_change_host" not in device.pending_steps


def test_change_host_noop_on_timeout():
    device = _make_device(pending={"resolve_change_host"})
    topics = _make_topics()
    task = ChangeHostFeatureTask(device, topics)

    # Monkey-patch wait to return None immediately
    task._wait_response = lambda timeout=2.0: None
    task.doTask()

    assert FEATURE_CHANGE_HOST not in device.available_features
    assert "resolve_change_host" in device.pending_steps


def test_change_host_noop_on_error_response():
    device = _make_device(pending={"resolve_change_host"})
    topics = _make_topics()
    task = ChangeHostFeatureTask(device, topics)

    task._response_queue.put(HidppErrorEvent(slot=SLOT, pid=PID, sw_id=FEATURE_CHANGE_HOST_SW_ID, error_code=5))
    task.doTask()

    assert FEATURE_CHANGE_HOST not in device.available_features


def test_change_host_noop_when_feat_idx_is_zero():
    device = _make_device(pending={"resolve_change_host"})
    topics = _make_topics()
    task = ChangeHostFeatureTask(device, topics)

    task._response_queue.put(_response(FEATURE_CHANGE_HOST_SW_ID, 0))
    task.doTask()

    assert FEATURE_CHANGE_HOST not in device.available_features


def test_change_host_noop_when_feature_code_is_already_an_index():
    # resolve_feature_task checks `self._feature_code in available_features.values()`.
    # Feature codes (e.g. 0x1814) are far larger than any index (0-255), so this
    # path is only reachable if another feature's index happens to equal the code —
    # effectively never in normal use.  The test below confirms the condition does NOT
    # match for a typical {FEATURE_CHANGE_HOST: 9} entry, so the task proceeds normally.
    device = _make_device(
        pending={"resolve_change_host"},
        features={FEATURE_CHANGE_HOST: 9},
    )
    topics = _make_topics()
    task = ChangeHostFeatureTask(device, topics)
    task._wait_response = lambda timeout=2.0: None  # timeout immediately
    task.doTask()

    # Task sent the request (did not early-return) then timed out without updating features
    topics["write_topic"].publish.assert_called_once()
    assert device.available_features.get(FEATURE_CHANGE_HOST) == 9  # unchanged


# ── ReprogFeatureTask ────────────────────────────────────────────────────────


def test_reprog_resolves_feature_index():
    device = _make_device(pending={"resolve_reprog"})
    topics = _make_topics()
    task = ReprogFeatureTask(device, topics)

    task._response_queue.put(_response(FEATURE_REPROG_CONTROLS_V4_SW_ID, 8))
    task.doTask()

    assert device.available_features.get(FEATURE_REPROG_CONTROLS_V4) == 8
    assert "resolve_reprog" not in device.pending_steps


def test_reprog_fires_dependent_steps(mocker):
    device = _make_device(pending={"resolve_reprog"})
    topics = _make_topics()
    task = ReprogFeatureTask(device, topics)

    mock_find = mocker.patch("cleverswitch.subscriber.task.feature.reprog_feature_task.FindDivertableCidsTask")
    task._fire_dependent_steps()

    mock_find.assert_called_once_with(device, topics)
    mock_find.return_value.start.assert_called_once()


# ── NameAndTypeFeatureTask ────────────────────────────────────────────────────


def test_name_and_type_resolves_feature_index():
    device = _make_device(pending={"resolve_x0005"})
    topics = _make_topics()
    task = NameAndTypeFeatureTask(device, topics)

    task._response_queue.put(_response(FEATURE_DEVICE_TYPE_AND_NAME_SW_ID, 5))
    task.doTask()

    assert device.available_features.get(FEATURE_DEVICE_TYPE_AND_NAME) == 5
    assert "resolve_x0005" not in device.pending_steps


def test_name_and_type_fires_dependent_steps(mocker):
    device = _make_device(pending={"resolve_x0005"})
    topics = _make_topics()
    task = NameAndTypeFeatureTask(device, topics)

    mock_type = mocker.patch("cleverswitch.subscriber.task.feature.name_and_type_feature_task.GetDeviceTypeTask")
    mock_name = mocker.patch("cleverswitch.subscriber.task.feature.name_and_type_feature_task.GetDeviceNameTask")
    task._fire_dependent_steps()

    mock_type.assert_called_once_with(device, topics)
    mock_type.return_value.start.assert_called_once()
    mock_name.assert_called_once_with(device, topics)
    mock_name.return_value.start.assert_called_once()
