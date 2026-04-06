"""Unit tests for subscriber/task/find_divertable_cids_task.py."""

from __future__ import annotations

import struct
from unittest.mock import MagicMock

from cleverswitch.event.hidpp_error_event import HidppErrorEvent
from cleverswitch.event.hidpp_response_event import HidppResponseEvent
from cleverswitch.hidpp.constants import BOLT_PID, FEATURE_CHANGE_HOST, FEATURE_REPROG_CONTROLS_V4, KEY_FLAG_DIVERTABLE, KEY_FLAG_PERSISTENTLY_DIVERTABLE
from cleverswitch.model.logi_device import LogiDevice
from cleverswitch.subscriber.task.constants import FIND_DIVERTABLE_CIDS_SW_ID
from cleverswitch.subscriber.task.find_divertable_cids_task import FindDivertableCidsTask
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics

PID = BOLT_PID
SLOT = 1
REPROG_IDX = 8


def _make_device(reprog_idx=REPROG_IDX, pending=None):
    features = {FEATURE_CHANGE_HOST: 9}
    if reprog_idx is not None:
        features[FEATURE_REPROG_CONTROLS_V4] = reprog_idx
    d = LogiDevice(wpid=0x407B, pid=PID, slot=SLOT, role="keyboard", available_features=features)
    if pending is not None:
        d.pending_steps = set(pending)
    return d


def _make_topics():
    return Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        divert=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
    )


def _count_response(count: int):
    payload = bytes([count]) + bytes(15)
    return HidppResponseEvent(slot=SLOT, pid=PID, feature_index=0, function=0, sw_id=FIND_DIVERTABLE_CIDS_SW_ID, payload=payload)


def _cid_info_response(cid: int, flags: int):
    # payload[0:2] = CID, payload[4] = flags
    payload = bytes([(cid >> 8) & 0xFF, cid & 0xFF, 0x00, 0x00, flags]) + bytes(11)
    return HidppResponseEvent(slot=SLOT, pid=PID, feature_index=0, function=0, sw_id=FIND_DIVERTABLE_CIDS_SW_ID, payload=payload)


# ── Happy path ────────────────────────────────────────────────────────────────


def test_finds_divertable_es_cids():
    device = _make_device(pending={"find_divertable_cids"})
    topics = _make_topics()
    task = FindDivertableCidsTask(device, topics)

    # count=1, then CID 0x00D1 with DIVERTABLE flag
    task._response_queue.put(_count_response(1))
    task._response_queue.put(_cid_info_response(0x00D1, KEY_FLAG_DIVERTABLE))
    task.doTask()

    assert 0x00D1 in device.divertable_cids
    assert "find_divertable_cids" not in device.pending_steps
    topics.divert.publish.assert_called_once()


def test_finds_persistently_divertable_es_cids():
    device = _make_device(pending={"find_divertable_cids"})
    topics = _make_topics()
    task = FindDivertableCidsTask(device, topics)

    task._response_queue.put(_count_response(1))
    task._response_queue.put(_cid_info_response(0x00D2, KEY_FLAG_DIVERTABLE | KEY_FLAG_PERSISTENTLY_DIVERTABLE))
    task.doTask()

    assert 0x00D2 in device.divertable_cids
    assert 0x00D2 in device.persistently_divertable_cids


def test_skips_non_es_cids():
    device = _make_device(pending={"find_divertable_cids"})
    topics = _make_topics()
    task = FindDivertableCidsTask(device, topics)

    task._response_queue.put(_count_response(1))
    task._response_queue.put(_cid_info_response(0x00AA, KEY_FLAG_DIVERTABLE))  # non-ES CID
    task.doTask()

    assert len(device.divertable_cids) == 0
    topics.divert.publish.assert_not_called()


def test_no_divert_published_when_no_divertable_cids():
    device = _make_device(pending={"find_divertable_cids"})
    topics = _make_topics()
    task = FindDivertableCidsTask(device, topics)

    task._response_queue.put(_count_response(0))
    task.doTask()

    topics.divert.publish.assert_not_called()


# ── Missing reprog feature ────────────────────────────────────────────────────


def test_returns_early_when_reprog_feature_missing():
    device = _make_device(reprog_idx=None, pending={"find_divertable_cids"})
    topics = _make_topics()
    task = FindDivertableCidsTask(device, topics)

    task.doTask()

    topics.write.publish.assert_not_called()


# ── Error / timeout handling ──────────────────────────────────────────────────


def test_returns_early_on_count_timeout():
    device = _make_device(pending={"find_divertable_cids"})
    topics = _make_topics()
    task = FindDivertableCidsTask(device, topics)

    task._wait_response = lambda timeout=2.0: None
    task.doTask()

    assert len(device.divertable_cids) == 0


def test_returns_early_on_count_error():
    device = _make_device(pending={"find_divertable_cids"})
    topics = _make_topics()
    task = FindDivertableCidsTask(device, topics)

    task._response_queue.put(HidppErrorEvent(slot=SLOT, pid=PID, sw_id=FIND_DIVERTABLE_CIDS_SW_ID, error_code=5))
    task.doTask()

    assert len(device.divertable_cids) == 0


def test_incomplete_scan_keeps_step_pending():
    device = _make_device(pending={"find_divertable_cids"})
    topics = _make_topics()
    task = FindDivertableCidsTask(device, topics)

    responses = [_count_response(2), _cid_info_response(0x00D1, KEY_FLAG_DIVERTABLE), None]
    idx = [0]

    def fake_wait(timeout=2.0):
        r = responses[idx[0]]
        idx[0] += 1
        return r

    task._wait_response = fake_wait
    task.doTask()

    assert "find_divertable_cids" in device.pending_steps
