"""Unit tests for subscriber/task/get_device_name_task.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from cleverswitch.event.hidpp_error_event import HidppErrorEvent
from cleverswitch.event.hidpp_response_event import HidppResponseEvent
from cleverswitch.hidpp.constants import BOLT_PID, FEATURE_DEVICE_TYPE_AND_NAME
from cleverswitch.model.logi_device import LogiDevice
from cleverswitch.subscriber.task.constants import GET_DEVICE_NAME_SW_ID
from cleverswitch.subscriber.task.get_device_name_task import GetDeviceNameTask
from cleverswitch.topic.topic import Topic

PID = BOLT_PID
SLOT = 1
NAME_IDX = 5


def _make_device(name=None, pending=None, features=None):
    d = LogiDevice(
        wpid=0x407B, pid=PID, slot=SLOT, role="keyboard",
        available_features=features if features is not None else {FEATURE_DEVICE_TYPE_AND_NAME: NAME_IDX},
        name=name,
    )
    if pending is not None:
        d.pending_steps = set(pending)
    return d


def _make_topics():
    return {
        "event_topic": MagicMock(spec=Topic),
        "write_topic": MagicMock(spec=Topic),
        "device_info_topic": MagicMock(spec=Topic),
        "divert_topic": MagicMock(spec=Topic),
        "info_progress_topic": MagicMock(spec=Topic),
    }


def _response(payload: bytes):
    return HidppResponseEvent(slot=SLOT, pid=PID, feature_index=0, function=0, sw_id=GET_DEVICE_NAME_SW_ID, payload=payload + bytes(16 - len(payload)))


def test_reads_device_name():
    device = _make_device(pending={"get_device_name"})
    topics = _make_topics()
    task = GetDeviceNameTask(device, topics)

    name = b"MX Keys"
    task._response_queue.put(_response(bytes([len(name)])))       # count response
    task._response_queue.put(_response(name))                      # name chunk
    task.doTask()

    assert device.name == "MX Keys"
    assert "get_device_name" not in device.pending_steps


def test_assembles_name_from_multiple_chunks():
    device = _make_device(pending={"get_device_name"})
    topics = _make_topics()
    task = GetDeviceNameTask(device, topics)

    # 17-char name forces two requests: first fills the 16-byte payload, second fetches the last char
    name = b"MX Master 3S Key"  # 16 chars in first chunk
    last = b"s"                 # 1 char in second chunk (total 17)
    full = name + last
    task._response_queue.put(_response(bytes([len(full)])))
    task._response_queue.put(_response(name))    # charIndex=0, fills all 16 payload bytes
    task._response_queue.put(_response(last))    # charIndex=16, 1 remaining char
    task.doTask()

    assert device.name == "MX Master 3S Keys"


def test_skips_when_name_already_known():
    device = _make_device(name="MX Keys", pending={"get_device_name"})
    topics = _make_topics()
    task = GetDeviceNameTask(device, topics)

    task.doTask()

    topics["write_topic"].publish.assert_not_called()
    assert "get_device_name" not in device.pending_steps


def test_skips_when_feature_not_available():
    device = _make_device(pending={"get_device_name"}, features={})
    topics = _make_topics()
    device.pending_steps.discard("resolve_x0005")
    task = GetDeviceNameTask(device, topics)

    task.doTask()

    assert "get_device_name" not in device.pending_steps


def test_sets_name_none_on_count_error():
    device = _make_device(pending={"get_device_name"})
    topics = _make_topics()
    task = GetDeviceNameTask(device, topics)

    task._response_queue.put(HidppErrorEvent(slot=SLOT, pid=PID, sw_id=GET_DEVICE_NAME_SW_ID, error_code=5))
    task.doTask()

    assert device.name is None


def test_sets_name_none_on_count_timeout():
    device = _make_device(pending={"get_device_name"})
    topics = _make_topics()
    task = GetDeviceNameTask(device, topics)

    task._wait_response = lambda timeout=2.0: None
    task.doTask()

    assert device.name is None


def test_discards_step_when_count_is_zero():
    device = _make_device(pending={"get_device_name"})
    topics = _make_topics()
    task = GetDeviceNameTask(device, topics)

    task._response_queue.put(_response(bytes([0])))
    task.doTask()

    assert "get_device_name" not in device.pending_steps


def test_sets_name_none_on_chunk_error():
    device = _make_device(pending={"get_device_name"})
    topics = _make_topics()
    task = GetDeviceNameTask(device, topics)

    task._response_queue.put(_response(bytes([7])))  # name len=7
    task._response_queue.put(HidppErrorEvent(slot=SLOT, pid=PID, sw_id=GET_DEVICE_NAME_SW_ID, error_code=5))
    task.doTask()

    assert device.name is None
