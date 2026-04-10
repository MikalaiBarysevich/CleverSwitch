"""Unit tests for subscriber/task/find_es_cids_flags_task.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from cleverswitch.event.hidpp_error_event import HidppErrorEvent
from cleverswitch.event.hidpp_response_event import HidppResponseEvent
from cleverswitch.event.set_report_flag_event import SetReportFlagEvent
from cleverswitch.hidpp.constants import (
    BOLT_PID,
    FEATURE_CHANGE_HOST,
    FEATURE_REPROG_CONTROLS_V4,
    KEY_FLAG_ANALYTICS,
    KEY_FLAG_DIVERTABLE,
    KEY_FLAG_PERSISTENTLY_DIVERTABLE,
)
from cleverswitch.model.logi_device import LogiDevice
from cleverswitch.subscriber.task.constants import FIND_ES_CIDS_FLAGS_SW_ID
from cleverswitch.subscriber.task.find_es_cids_flags_task import FindESCidsFlagsTask
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
        flags=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
    )


def _count_response(count: int):
    payload = bytes([count]) + bytes(15)
    return HidppResponseEvent(slot=SLOT, pid=PID, feature_index=0, function=0, sw_id=FIND_ES_CIDS_FLAGS_SW_ID, payload=payload)


def _cid_info_response(cid: int, flags: int):
    body = bytes([(cid >> 8) & 0xFF, cid & 0xFF, 0x00, 0x00, flags]) + bytes(11)
    return HidppResponseEvent(slot=SLOT, pid=PID, feature_index=0, function=0, sw_id=FIND_ES_CIDS_FLAGS_SW_ID, payload=body)


# ── Happy path: both KEY_FLAG_ANALYTICS and KEY_FLAG_DIVERTABLE ───────────────


def test_both_analytics_and_divertable_flags_publish_set_report_flag_event():
    """Both KEY_FLAG_ANALYTICS and KEY_FLAG_DIVERTABLE present → publishes SetReportFlagEvent."""
    device = _make_device(pending={"find_es_cids_flags"})
    topics = _make_topics()
    task = FindESCidsFlagsTask(device, topics)

    task._response_queue.put(_count_response(1))
    task._response_queue.put(_cid_info_response(0x00D2, KEY_FLAG_ANALYTICS | KEY_FLAG_DIVERTABLE))
    task.doTask()

    assert KEY_FLAG_ANALYTICS in device.supported_flags
    assert KEY_FLAG_DIVERTABLE in device.supported_flags
    topics.flags.publish.assert_called_once()
    published = topics.flags.publish.call_args[0][0]
    assert isinstance(published, SetReportFlagEvent)


# ── KEY_FLAG_ANALYTICS only → publishes (analytics mode works standalone) ─────


def test_analytics_flag_only_publishes():
    """Only KEY_FLAG_ANALYTICS → publishes SetReportFlagEvent (analytics mode works alone)."""
    device = _make_device(pending={"find_es_cids_flags"})
    topics = _make_topics()
    task = FindESCidsFlagsTask(device, topics)

    task._response_queue.put(_count_response(1))
    task._response_queue.put(_cid_info_response(0x00D2, KEY_FLAG_ANALYTICS))
    task.doTask()

    assert KEY_FLAG_ANALYTICS in device.supported_flags
    topics.flags.publish.assert_called_once()
    assert isinstance(topics.flags.publish.call_args[0][0], SetReportFlagEvent)


# ── KEY_FLAG_DIVERTABLE only → publishes (divert mode works standalone) ───────


def test_divertable_flag_only_publishes():
    """Only KEY_FLAG_DIVERTABLE → publishes SetReportFlagEvent (divert mode works alone)."""
    device = _make_device(pending={"find_es_cids_flags"})
    topics = _make_topics()
    task = FindESCidsFlagsTask(device, topics)

    task._response_queue.put(_count_response(1))
    task._response_queue.put(_cid_info_response(0x00D1, KEY_FLAG_DIVERTABLE))
    task.doTask()

    assert KEY_FLAG_DIVERTABLE in device.supported_flags
    topics.flags.publish.assert_called_once()
    assert isinstance(topics.flags.publish.call_args[0][0], SetReportFlagEvent)


# ── KEY_FLAG_PERSISTENTLY_DIVERTABLE added when present ──────────────────────


def test_persistently_divertable_flag_added_to_supported_flags():
    device = _make_device(pending={"find_es_cids_flags"})
    topics = _make_topics()
    task = FindESCidsFlagsTask(device, topics)

    task._response_queue.put(_count_response(1))
    task._response_queue.put(_cid_info_response(0x00D1, KEY_FLAG_DIVERTABLE | KEY_FLAG_PERSISTENTLY_DIVERTABLE))
    task.doTask()

    assert KEY_FLAG_PERSISTENTLY_DIVERTABLE in device.supported_flags


# ── No flags → no publish, logs error ────────────────────────────────────────


def test_es_cid_with_no_flags_no_publish():
    device = _make_device(pending={"find_es_cids_flags"})
    topics = _make_topics()
    task = FindESCidsFlagsTask(device, topics)

    task._response_queue.put(_count_response(1))
    task._response_queue.put(_cid_info_response(0x00D2, 0))
    task.doTask()

    topics.flags.publish.assert_not_called()


# ── Timeout on getCount → step stays pending ─────────────────────────────────


def test_timeout_on_count_no_publish_step_pending():
    device = _make_device(pending={"find_es_cids_flags"})
    topics = _make_topics()
    task = FindESCidsFlagsTask(device, topics)

    task._wait_response = lambda timeout=2.0: None
    task.doTask()

    topics.flags.publish.assert_not_called()
    assert "find_es_cids_flags" in device.pending_steps


# ── Timeout on getCidInfo → incomplete scan, step stays pending ───────────────


def test_timeout_on_cid_info_keeps_step_pending():
    device = _make_device(pending={"find_es_cids_flags"})
    topics = _make_topics()
    task = FindESCidsFlagsTask(device, topics)

    # count=1 and the only getCidInfo times out → cid_seen stays False → step stays pending
    responses = [_count_response(1), None]
    idx = [0]

    def fake_wait(timeout=2.0):
        r = responses[idx[0]]
        idx[0] += 1
        return r

    task._wait_response = fake_wait
    task.doTask()

    assert "find_es_cids_flags" in device.pending_steps
    topics.flags.publish.assert_not_called()


# ── Step already complete → skipped ──────────────────────────────────────────


def test_step_already_complete_skips_dotask():
    device = _make_device(pending=set())  # "find_es_cids_flags" not in pending_steps
    topics = _make_topics()
    task = FindESCidsFlagsTask(device, topics)

    task.run()

    topics.write.publish.assert_not_called()
    topics.flags.publish.assert_not_called()
