"""Unit tests for subscriber/task/get_device_type_task.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from cleverswitch.event.hidpp_error_event import HidppErrorEvent
from cleverswitch.event.hidpp_response_event import HidppResponseEvent
from cleverswitch.hidpp.constants import BOLT_PID, FEATURE_DEVICE_TYPE_AND_NAME
from cleverswitch.model.logi_device import LogiDevice
from cleverswitch.subscriber.task.constants import GET_DEVICE_TYPE_SW_ID
from cleverswitch.subscriber.task.get_device_type_task import GetDeviceTypeTask
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics

PID = BOLT_PID
SLOT = 1
NAME_IDX = 5


def _make_device(role=None, pending=None, features=None):
    d = LogiDevice(
        wpid=0x407B, pid=PID, slot=SLOT, role=role,
        available_features=features if features is not None else {FEATURE_DEVICE_TYPE_AND_NAME: NAME_IDX},
    )
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


def _type_response(device_type: int):
    payload = bytes([device_type]) + bytes(15)
    return HidppResponseEvent(slot=SLOT, pid=PID, feature_index=0, function=0, sw_id=GET_DEVICE_TYPE_SW_ID, payload=payload)


def test_sets_role_keyboard_for_type_0():
    device = _make_device(pending={"get_device_type"})
    topics = _make_topics()
    task = GetDeviceTypeTask(device, topics)

    task._response_queue.put(_type_response(0))
    task.doTask()

    assert device.role == "keyboard"
    assert "get_device_type" not in device.pending_steps


def test_sets_role_mouse_for_non_zero_type():
    device = _make_device(pending={"get_device_type"})
    topics = _make_topics()
    task = GetDeviceTypeTask(device, topics)

    task._response_queue.put(_type_response(3))
    task.doTask()

    assert device.role == "mouse"


def test_skips_when_role_already_known():
    device = _make_device(role="keyboard", pending={"get_device_type"})
    topics = _make_topics()
    task = GetDeviceTypeTask(device, topics)

    task.doTask()

    topics.write.publish.assert_not_called()
    assert "get_device_type" not in device.pending_steps


def test_skips_when_feature_not_available():
    device = _make_device(pending={"get_device_type"}, features={})
    topics = _make_topics()
    # resolve_x0005 NOT in pending → feature is just unsupported
    device.pending_steps.discard("resolve_x0005")
    task = GetDeviceTypeTask(device, topics)

    task.doTask()

    assert device.role is None
    assert "get_device_type" not in device.pending_steps


def test_discards_step_on_error_response():
    device = _make_device(pending={"get_device_type"})
    topics = _make_topics()
    task = GetDeviceTypeTask(device, topics)

    task._response_queue.put(HidppErrorEvent(slot=SLOT, pid=PID, sw_id=GET_DEVICE_TYPE_SW_ID, error_code=5))
    task.doTask()

    assert device.role is None
    assert "get_device_type" not in device.pending_steps


def test_keeps_step_pending_on_timeout():
    device = _make_device(pending={"get_device_type"})
    topics = _make_topics()
    task = GetDeviceTypeTask(device, topics)

    task._wait_response = lambda timeout=2.0: None
    task.doTask()

    assert device.role is None
    assert "get_device_type" in device.pending_steps
