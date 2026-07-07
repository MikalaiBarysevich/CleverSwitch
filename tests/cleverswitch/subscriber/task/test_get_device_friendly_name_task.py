"""Unit tests for subscriber/task/get_device_friendly_name_task.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.cleverswitch.event.hidpp_error_event import HidppErrorEvent
from src.cleverswitch.event.hidpp_response_event import HidppResponseEvent
from src.cleverswitch.hidpp.constants import BOLT_PID, FEATURE_DEVICE_FRIENDLY_NAME
from src.cleverswitch.model.logi_device import LogiDevice
from src.cleverswitch.subscriber.task.constants import GET_DEVICE_FRIENDLY_NAME_SW_ID, Task
from src.cleverswitch.subscriber.task.get_device_friendly_name_task import GetDeviceFriendlyNameTask
from src.cleverswitch.topic.topic import Topic
from src.cleverswitch.topic.topics import Topics

PID = BOLT_PID
SLOT = 1
FRIENDLY_IDX = 3


def _make_device(friendly_name=None, pending=None, features=None):
    d = LogiDevice(
        wpid=0x407B,
        pid=PID,
        slot=SLOT,
        role="keyboard",
        available_features=features if features is not None else {FEATURE_DEVICE_FRIENDLY_NAME: FRIENDLY_IDX},
    )
    d.friendly_name = friendly_name
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
        sw_id=GET_DEVICE_FRIENDLY_NAME_SW_ID,
        payload=payload + bytes(16 - len(payload)),
    )


def test_reads_friendly_name_single_chunk():
    device = _make_device(pending={Task.Name.GET_DEVICE_FRIENDLY_NAME})
    topics = _make_topics()
    task = GetDeviceFriendlyNameTask(device, topics)

    name = b"MX Keys"
    task._response_queue.put(_response(bytes([len(name), 15, len(name)])))  # nameLen, nameMaxLen, defaultNameLen
    # fn=1 response: byte 0 echoes byteIndex (0), bytes 1..15 carry the name chunk
    task._response_queue.put(_response(bytes([0]) + name))
    task.doTask()

    assert device.friendly_name == "MX Keys"
    assert Task.Name.GET_DEVICE_FRIENDLY_NAME not in device.pending_steps


def test_assembles_friendly_name_from_multiple_chunks():
    device = _make_device(pending={Task.Name.GET_DEVICE_FRIENDLY_NAME})
    topics = _make_topics()
    task = GetDeviceFriendlyNameTask(device, topics)

    # 20-char name needs two fn=1 calls: byteIndex=0 (15 bytes), byteIndex=15 (5 bytes)
    full_name = b"MX Master 3S Keys   "  # 20 chars
    name_len = len(full_name)
    first_chunk = full_name[:15]  # "MX Master 3S Ke"
    second_chunk = full_name[15:]  # "ys   "

    task._response_queue.put(_response(bytes([name_len, 30, name_len])))
    # Each fn=1 response: byte 0 = echoed byteIndex, bytes 1..15 = chunk
    task._response_queue.put(_response(bytes([0]) + first_chunk))
    task._response_queue.put(_response(bytes([15]) + second_chunk))
    task.doTask()

    assert device.friendly_name == full_name.decode().strip()
    assert Task.Name.GET_DEVICE_FRIENDLY_NAME not in device.pending_steps

    # Verify three writes total: len request, chunk@0, chunk@15
    calls = topics.write.publish.call_args_list
    assert len(calls) == 3
    # The second fn=1 request must carry byteIndex=15 in its payload (byte 4 of long report)
    second_write_msg = calls[2].args[0].hid_message
    assert second_write_msg[4] == 15


def test_strips_nul_padding_from_friendly_name():
    device = _make_device(pending={Task.Name.GET_DEVICE_FRIENDLY_NAME})
    topics = _make_topics()
    task = GetDeviceFriendlyNameTask(device, topics)

    # firmware reports len 10 but pads the tail with NULs (_response zero-fills after the chunk)
    task._response_queue.put(_response(bytes([10, 15, 10])))
    task._response_queue.put(_response(bytes([0]) + b"MX Keys"))  # 7 real chars + 3 NUL pad bytes read
    task.doTask()

    assert device.friendly_name == "MX Keys"
    assert Task.Name.GET_DEVICE_FRIENDLY_NAME not in device.pending_steps


def test_feature_unavailable_and_feature_step_done_discards_step():
    device = _make_device(pending={Task.Name.GET_DEVICE_FRIENDLY_NAME}, features={})
    topics = _make_topics()
    # Feature step already resolved (not in pending)
    device.pending_steps.discard(Task.Feature.Name.FRIENDLY_NAME)
    task = GetDeviceFriendlyNameTask(device, topics)

    task.doTask()

    topics.write.publish.assert_not_called()
    assert Task.Name.GET_DEVICE_FRIENDLY_NAME not in device.pending_steps
    assert device.friendly_name is None


def test_feature_unavailable_and_feature_step_still_pending_is_noop():
    device = _make_device(pending={Task.Name.GET_DEVICE_FRIENDLY_NAME, Task.Feature.Name.FRIENDLY_NAME}, features={})
    topics = _make_topics()
    task = GetDeviceFriendlyNameTask(device, topics)

    task.doTask()

    topics.write.publish.assert_not_called()
    assert Task.Name.GET_DEVICE_FRIENDLY_NAME in device.pending_steps


def test_timeout_on_get_len_leaves_step_pending():
    device = _make_device(pending={Task.Name.GET_DEVICE_FRIENDLY_NAME})
    topics = _make_topics()
    task = GetDeviceFriendlyNameTask(device, topics)

    task._wait_response = lambda timeout=2.0: None
    task.doTask()

    assert device.friendly_name is None
    assert Task.Name.GET_DEVICE_FRIENDLY_NAME in device.pending_steps


def test_error_on_get_len_leaves_step_pending():
    device = _make_device(pending={Task.Name.GET_DEVICE_FRIENDLY_NAME})
    topics = _make_topics()
    task = GetDeviceFriendlyNameTask(device, topics)

    task._response_queue.put(HidppErrorEvent(slot=SLOT, pid=PID, sw_id=GET_DEVICE_FRIENDLY_NAME_SW_ID, error_code=5))
    task.doTask()

    assert device.friendly_name is None
    assert Task.Name.GET_DEVICE_FRIENDLY_NAME in device.pending_steps


def test_early_exit_when_friendly_name_already_set():
    device = _make_device(friendly_name="MX Keys", pending={Task.Name.GET_DEVICE_FRIENDLY_NAME})
    topics = _make_topics()
    task = GetDeviceFriendlyNameTask(device, topics)

    task.doTask()

    topics.write.publish.assert_not_called()
    assert Task.Name.GET_DEVICE_FRIENDLY_NAME not in device.pending_steps
    assert device.friendly_name == "MX Keys"


def test_discards_step_when_name_len_is_zero():
    device = _make_device(pending={Task.Name.GET_DEVICE_FRIENDLY_NAME})
    topics = _make_topics()
    task = GetDeviceFriendlyNameTask(device, topics)

    task._response_queue.put(_response(bytes([0, 15, 0])))
    task.doTask()

    assert Task.Name.GET_DEVICE_FRIENDLY_NAME not in device.pending_steps
    assert device.friendly_name is None


def test_chunk_error_leaves_friendly_name_none():
    device = _make_device(pending={Task.Name.GET_DEVICE_FRIENDLY_NAME})
    topics = _make_topics()
    task = GetDeviceFriendlyNameTask(device, topics)

    task._response_queue.put(_response(bytes([7, 15, 7])))
    task._response_queue.put(HidppErrorEvent(slot=SLOT, pid=PID, sw_id=GET_DEVICE_FRIENDLY_NAME_SW_ID, error_code=5))
    task.doTask()

    assert device.friendly_name is None
