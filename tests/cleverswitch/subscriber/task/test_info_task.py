"""Unit tests for subscriber/task/info_task.py — InfoTask base class."""

from __future__ import annotations

from unittest.mock import MagicMock

from cleverswitch.event.hidpp_error_event import HidppErrorEvent
from cleverswitch.event.hidpp_response_event import HidppResponseEvent
from cleverswitch.hidpp.constants import BOLT_PID
from cleverswitch.model.logi_device import LogiDevice
from cleverswitch.subscriber.task.info_task import InfoTask
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics

PID = BOLT_PID
SLOT = 1
SW_ID = 0x09


def _make_device(pending=None):
    d = LogiDevice(wpid=0x407B, pid=PID, slot=SLOT, role="keyboard", available_features={})
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


class _ConcreteTask(InfoTask):
    """Minimal concrete InfoTask for testing."""

    def __init__(self, device, topics, step_name="test_step", do_task_fn=None):
        super().__init__(step_name, device, topics, request_id=0x0000, sw_id=SW_ID)
        self._do_task_fn = do_task_fn

    def doTask(self):
        if self._do_task_fn:
            self._do_task_fn()


# ── notify() ──────────────────────────────────────────────────────────────────


def test_notify_enqueues_matching_response():
    device = _make_device()
    topics = _make_topics()
    task = _ConcreteTask(device, topics)

    response = HidppResponseEvent(slot=SLOT, pid=PID, feature_index=0, function=0, sw_id=SW_ID, payload=bytes(16))
    task.notify(response)

    result = task._wait_response(timeout=0.1)
    assert result is response


def test_notify_enqueues_error_event_for_same_slot():
    device = _make_device()
    topics = _make_topics()
    task = _ConcreteTask(device, topics)

    error = HidppErrorEvent(slot=SLOT, pid=PID, sw_id=SW_ID, error_code=5)
    task.notify(error)

    result = task._wait_response(timeout=0.1)
    assert result is error


def test_notify_ignores_response_with_wrong_sw_id():
    device = _make_device()
    topics = _make_topics()
    task = _ConcreteTask(device, topics)

    response = HidppResponseEvent(slot=SLOT, pid=PID, feature_index=0, function=0, sw_id=0x0F, payload=bytes(16))
    task.notify(response)

    result = task._wait_response(timeout=0.05)
    assert result is None


def test_notify_ignores_response_from_wrong_slot():
    device = _make_device()
    topics = _make_topics()
    task = _ConcreteTask(device, topics)

    response = HidppResponseEvent(slot=99, pid=PID, feature_index=0, function=0, sw_id=SW_ID, payload=bytes(16))
    task.notify(response)

    result = task._wait_response(timeout=0.05)
    assert result is None


def test_notify_ignores_unrelated_event():
    device = _make_device()
    topics = _make_topics()
    task = _ConcreteTask(device, topics)
    task.notify("not an event")  # must not raise


# ── run() ─────────────────────────────────────────────────────────────────────


def test_run_publishes_success_and_fires_dependents_when_dotask_completes():
    device = _make_device(pending={"test_step"})
    topics = _make_topics()
    fired = []

    class _TaskWithDependent(_ConcreteTask):
        def _fire_dependent_steps(self):
            fired.append(1)

    def do_task_fn():
        device.pending_steps.discard("test_step")

    task = _TaskWithDependent(device, topics, step_name="test_step", do_task_fn=do_task_fn)
    task.run()

    assert fired == [1]
    topics.info_progress.publish.assert_called_once()
    event = topics.info_progress.publish.call_args[0][0]
    assert event.success is True
    assert event.step_name == "test_step"


def test_run_publishes_failure_and_no_dependents_when_dotask_times_out():
    device = _make_device(pending={"test_step"})
    topics = _make_topics()
    fired = []

    class _TaskWithDependent(_ConcreteTask):
        def _fire_dependent_steps(self):
            fired.append(1)

    task = _TaskWithDependent(device, topics, step_name="test_step")
    task.run()

    assert fired == []
    topics.info_progress.publish.assert_called_once()
    event = topics.info_progress.publish.call_args[0][0]
    assert event.success is False
    assert event.step_name == "test_step"


def test_run_publishes_success_without_calling_dotask_when_already_done():
    device = _make_device(pending=set())  # test_step not in pending
    topics = _make_topics()
    called = []

    task = _ConcreteTask(device, topics, step_name="test_step", do_task_fn=lambda: called.append(1))
    task.run()

    assert called == []
    topics.info_progress.publish.assert_called_once()
    event = topics.info_progress.publish.call_args[0][0]
    assert event.success is True


# ── _send_request() ───────────────────────────────────────────────────────────


def test_send_request_publishes_write_event():
    device = _make_device()
    topics = _make_topics()
    task = _ConcreteTask(device, topics)

    task._send_request(0x18, 0x14, 0x00)

    topics.write.publish.assert_called_once()


def test_send_request_with_custom_request_id():
    device = _make_device()
    topics = _make_topics()
    task = _ConcreteTask(device, topics)

    task._send_request(request_id=0x0500)

    topics.write.publish.assert_called_once()


# ── _wait_response() ──────────────────────────────────────────────────────────


def test_wait_response_returns_none_on_timeout():
    device = _make_device()
    topics = _make_topics()
    task = _ConcreteTask(device, topics)

    result = task._wait_response(timeout=0.05)
    assert result is None
