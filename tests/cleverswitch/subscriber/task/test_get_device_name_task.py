"""Unit tests for subscriber/task/get_device_name_task.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.cleverswitch.event.hidpp_error_event import HidppErrorEvent
from src.cleverswitch.event.hidpp_response_event import HidppResponseEvent
from src.cleverswitch.hidpp.constants import BOLT_PID, FEATURE_DEVICE_TYPE_AND_NAME
from src.cleverswitch.model.logi_device import LogiDevice
from src.cleverswitch.subscriber.task.constants import GET_DEVICE_NAME_SW_ID, Task
from src.cleverswitch.subscriber.task.get_device_name_task import GetDeviceNameTask
from src.cleverswitch.topic.topic import Topic
from src.cleverswitch.topic.topics import Topics
from tests.task_helpers import deliver_on_request

PID = BOLT_PID
SLOT = 1
NAME_IDX = 5


def _make_device(name=None, pending=None, features=None):
    d = LogiDevice(
        wpid=0x407B,
        pid=PID,
        slot=SLOT,
        role="keyboard",
        available_features=features if features is not None else {FEATURE_DEVICE_TYPE_AND_NAME: NAME_IDX},
        name=name,
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


def _response(payload: bytes):
    return HidppResponseEvent(
        slot=SLOT,
        pid=PID,
        feature_index=0,
        function=0,
        sw_id=GET_DEVICE_NAME_SW_ID,
        payload=payload + bytes(16 - len(payload)),
    )


def test_reads_device_name():
    device = _make_device(pending={Task.Name.GET_DEVICE_NAME})
    topics = _make_topics()
    task = GetDeviceNameTask(device, topics)

    name = b"MX Keys"
    # count response, then the name chunk
    deliver_on_request(task, topics, [_response(bytes([len(name)])), _response(name)])
    task.doTask()

    assert device.name == "MX Keys"
    assert Task.Name.GET_DEVICE_NAME not in device.pending_steps


def test_assembles_name_from_multiple_chunks():
    device = _make_device(pending={Task.Name.GET_DEVICE_NAME})
    topics = _make_topics()
    task = GetDeviceNameTask(device, topics)

    # 17-char name forces two requests: first fills the 16-byte payload, second fetches the last char
    name = b"MX Master 3S Key"  # 16 chars in first chunk
    last = b"s"  # 1 char in second chunk (total 17)
    full = name + last
    # count, then charIndex=0 filling all 16 payload bytes, then charIndex=16 with the last char
    deliver_on_request(task, topics, [_response(bytes([len(full)])), _response(name), _response(last)])
    task.doTask()

    assert device.name == "MX Master 3S Keys"


def test_strips_nul_padding_from_name():
    device = _make_device(pending={Task.Name.GET_DEVICE_NAME})
    topics = _make_topics()
    task = GetDeviceNameTask(device, topics)

    # firmware reports a count of 10 but pads the tail with NULs (_response zero-fills)
    # count=10, then a chunk of 7 real chars + 3 NUL pad bytes
    deliver_on_request(task, topics, [_response(bytes([10])), _response(b"MX Keys")])
    task.doTask()

    assert device.name == "MX Keys"
    assert Task.Name.GET_DEVICE_NAME not in device.pending_steps


def test_skips_when_name_already_known():
    device = _make_device(name="MX Keys", pending={Task.Name.GET_DEVICE_NAME})
    topics = _make_topics()
    task = GetDeviceNameTask(device, topics)

    task.doTask()

    topics.write.publish.assert_not_called()
    assert Task.Name.GET_DEVICE_NAME not in device.pending_steps


def test_skips_when_feature_not_available():
    device = _make_device(pending={Task.Name.GET_DEVICE_NAME}, features={})
    topics = _make_topics()
    device.pending_steps.discard(Task.Feature.Name.NAME_AND_TYPE)
    task = GetDeviceNameTask(device, topics)

    task.doTask()

    assert Task.Name.GET_DEVICE_NAME not in device.pending_steps


def test_sets_name_none_on_count_error():
    device = _make_device(pending={Task.Name.GET_DEVICE_NAME})
    topics = _make_topics()
    task = GetDeviceNameTask(device, topics)

    deliver_on_request(task, topics, [HidppErrorEvent(slot=SLOT, pid=PID, sw_id=GET_DEVICE_NAME_SW_ID, error_code=5)])
    task.doTask()

    assert device.name is None


def test_sets_name_none_on_count_timeout():
    device = _make_device(pending={Task.Name.GET_DEVICE_NAME})
    topics = _make_topics()
    task = GetDeviceNameTask(device, topics)

    task._wait_response = lambda timeout=2.0: None
    task.doTask()

    assert device.name is None


def test_discards_step_when_count_is_zero():
    device = _make_device(pending={Task.Name.GET_DEVICE_NAME})
    topics = _make_topics()
    task = GetDeviceNameTask(device, topics)

    deliver_on_request(task, topics, [_response(bytes([0]))])
    task.doTask()

    assert Task.Name.GET_DEVICE_NAME not in device.pending_steps


def test_sets_name_none_on_chunk_error():
    device = _make_device(pending={Task.Name.GET_DEVICE_NAME})
    topics = _make_topics()
    task = GetDeviceNameTask(device, topics)

    # name len=7, then the chunk request errors out
    deliver_on_request(
        task,
        topics,
        [_response(bytes([7])), HidppErrorEvent(slot=SLOT, pid=PID, sw_id=GET_DEVICE_NAME_SW_ID, error_code=5)],
    )
    task.doTask()

    assert device.name is None
