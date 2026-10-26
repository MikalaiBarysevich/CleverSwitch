"""Unit tests for subscriber/task/info_task.py — InfoTask base class."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from cleverswitch.event.device_connected_event import DeviceConnectedEvent
from cleverswitch.event.hidpp_error_event import HidppErrorEvent
from cleverswitch.event.hidpp_response_event import HidppResponseEvent
from cleverswitch.event.transport_disconnected_event import TransportDisconnectedEvent
from cleverswitch.hidpp.constants import BOLT_PID
from cleverswitch.model.logi_device import ROLE_KEYBOARD, LogiDevice
from cleverswitch.subscriber.task.info_task import InfoTask
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics

PID = BOLT_PID
SLOT = 1
SW_ID = 0x09


def _make_device(pending=None):
    d = LogiDevice(wpid=0x407B, pid=PID, slot=SLOT, role=ROLE_KEYBOARD, available_features={})
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


def test_notify_enqueues_error_event_with_matching_slot_pid_sw_id():
    device = _make_device()
    topics = _make_topics()
    task = _ConcreteTask(device, topics)

    error = HidppErrorEvent(slot=SLOT, pid=PID, feature_index=0, function=0, sw_id=SW_ID, error_code=5)
    task.notify(error)

    result = task._wait_response(timeout=0.1)
    assert result is error


def test_notify_ignores_error_event_with_wrong_sw_id():
    device = _make_device()
    topics = _make_topics()
    task = _ConcreteTask(device, topics)

    error = HidppErrorEvent(slot=SLOT, pid=PID, feature_index=0, function=0, sw_id=0x0F, error_code=5)
    task.notify(error)

    result = task._wait_response(timeout=0.05)
    assert result is None


def test_notify_ignores_error_event_with_wrong_pid():
    device = _make_device()
    topics = _make_topics()
    task = _ConcreteTask(device, topics)

    error = HidppErrorEvent(slot=SLOT, pid=PID + 1, feature_index=0, function=0, sw_id=SW_ID, error_code=5)
    task.notify(error)

    result = task._wait_response(timeout=0.05)
    assert result is None


def test_notify_ignores_error_event_from_wrong_slot():
    device = _make_device()
    topics = _make_topics()
    task = _ConcreteTask(device, topics)

    error = HidppErrorEvent(slot=99, pid=PID, feature_index=0, function=0, sw_id=SW_ID, error_code=5)
    task.notify(error)

    result = task._wait_response(timeout=0.05)
    assert result is None


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


def test_run_publishes_failure_when_dotask_raises():
    device = _make_device(pending={"test_step"})
    topics = _make_topics()

    def raise_error():
        raise RuntimeError("boom")

    task = _ConcreteTask(device, topics, step_name="test_step", do_task_fn=raise_error)
    task.run()

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


# ── subscription lifecycle ────────────────────────────────────────────────────


def test_run_unsubscribes():
    device = _make_device(pending={"test_step"})
    topics = _make_topics()

    task = _ConcreteTask(device, topics, step_name="test_step")
    task.run()

    topics.hid_event.unsubscribe.assert_called_once_with(topics.hid_event.subscribe.return_value)


def test_run_unsubscribes_when_fire_dependent_steps_raises():
    device = _make_device(pending=set())
    topics = _make_topics()

    class _TaskWithFailingDependent(_ConcreteTask):
        def _fire_dependent_steps(self):
            raise RuntimeError("boom")

    task = _TaskWithFailingDependent(device, topics, step_name="test_step")
    with pytest.raises(RuntimeError):
        task.run()

    topics.hid_event.unsubscribe.assert_called_once_with(topics.hid_event.subscribe.return_value)


# ── _send_request drains stale responses ──────────────────────────────────────


def test_send_request_discards_a_response_queued_before_it():
    """A late reply must not be handed to the next request as if it were its answer."""
    device = _make_device()
    topics = _make_topics()
    task = _ConcreteTask(device, topics)

    stale = HidppResponseEvent(slot=SLOT, pid=PID, feature_index=3, function=1, sw_id=SW_ID, payload=b"stale")
    task._response_queue.put(stale)

    task._send_request()

    assert task._wait_response(timeout=0.01) is None


def test_send_request_discards_a_stale_error_event_too():
    device = _make_device()
    topics = _make_topics()
    task = _ConcreteTask(device, topics)

    task._response_queue.put(
        HidppErrorEvent(slot=SLOT, pid=PID, feature_index=0, function=0, sw_id=SW_ID, error_code=0x09)
    )

    task._send_request()

    assert task._wait_response(timeout=0.01) is None


def test_send_request_delivers_the_response_that_arrives_after_it():
    """The reply to *this* request still gets through."""
    device = _make_device()
    topics = _make_topics()
    task = _ConcreteTask(device, topics)

    fresh = HidppResponseEvent(slot=SLOT, pid=PID, feature_index=3, function=1, sw_id=SW_ID, payload=b"fresh")
    topics.write.publish.side_effect = lambda *_a, **_k: task._response_queue.put(fresh)

    task._send_request()

    assert task._wait_response(timeout=0.01) is fresh


# ── notify() matches the call just sent ──────────────────────────────────────


def test_notify_ignores_reply_to_a_different_call_with_our_sw_id():
    """A peer app reusing our sw_id must not have its replies taken as ours."""
    device = _make_device()
    topics = _make_topics()
    task = _ConcreteTask(device, topics)
    task._send_request(request_id=0x0310)

    peer = HidppResponseEvent(slot=SLOT, pid=PID, feature_index=0, function=0, sw_id=SW_ID, payload=bytes(16))
    task.notify(peer)

    assert task._wait_response(timeout=0.05) is None


def test_notify_enqueues_reply_to_the_call_just_sent():
    device = _make_device()
    topics = _make_topics()
    task = _ConcreteTask(device, topics)
    task._send_request(request_id=0x0310)

    reply = HidppResponseEvent(slot=SLOT, pid=PID, feature_index=3, function=1, sw_id=SW_ID, payload=bytes(16))
    task.notify(reply)

    assert task._wait_response(timeout=0.1) is reply


def test_notify_enqueues_error_for_the_call_just_sent():
    device = _make_device()
    topics = _make_topics()
    task = _ConcreteTask(device, topics)
    task._send_request(request_id=0x0310)

    error = HidppErrorEvent(slot=SLOT, pid=PID, feature_index=3, function=1, sw_id=SW_ID, error_code=5)
    task.notify(error)

    assert task._wait_response(timeout=0.1) is error


def test_notify_ignores_error_for_a_different_call():
    device = _make_device()
    topics = _make_topics()
    task = _ConcreteTask(device, topics)
    task._send_request(request_id=0x0310)

    error = HidppErrorEvent(slot=SLOT, pid=PID, feature_index=3, function=0, sw_id=SW_ID, error_code=5)
    task.notify(error)

    assert task._wait_response(timeout=0.05) is None


# ── abort on disconnect ──────────────────────────────────────────────────────


def _disconnect(device):
    return DeviceConnectedEvent(slot=device.slot, pid=device.pid, wpid=device.wpid, link_established=False)


def test_own_disconnect_wakes_a_waiting_task_with_none():
    device = _make_device()
    topics = _make_topics()
    task = _ConcreteTask(device, topics)
    task._send_request(request_id=0x0310)

    task.notify(_disconnect(device))

    assert task._wait_response(timeout=1.0) is None


def test_reply_after_own_disconnect_is_not_taken():
    """A reply to the request sent after reconnect must not reach the task that started before it."""
    device = _make_device()
    topics = _make_topics()
    task = _ConcreteTask(device, topics)
    task._send_request(request_id=0x0310)
    task.notify(_disconnect(device))
    task._wait_response(timeout=0.01)

    reply = HidppResponseEvent(slot=SLOT, pid=PID, feature_index=3, function=1, sw_id=SW_ID, payload=bytes(16))
    task.notify(reply)

    assert task._wait_response(timeout=0.05) is None


def test_transport_disconnect_for_device_pid_aborts():
    device = _make_device()
    topics = _make_topics()
    task = _ConcreteTask(device, topics)

    task.notify(TransportDisconnectedEvent(slot=0, pid=PID))

    assert task._aborted.is_set()


def test_disconnect_of_another_device_does_not_abort():
    device = _make_device()
    topics = _make_topics()
    task = _ConcreteTask(device, topics)

    task.notify(DeviceConnectedEvent(slot=2, pid=PID, wpid=0x4082, link_established=False))
    task.notify(TransportDisconnectedEvent(slot=0, pid=PID + 1))
    task.notify(DeviceConnectedEvent(slot=SLOT, pid=PID, wpid=device.wpid, link_established=True))

    assert not task._aborted.is_set()


def test_aborted_task_sends_no_more_requests():
    device = _make_device()
    topics = _make_topics()
    task = _ConcreteTask(device, topics)
    task.notify(_disconnect(device))

    task._send_request(request_id=0x0310)

    topics.write.publish.assert_not_called()


def test_run_reports_aborted_failure():
    device = _make_device(pending={"test_step"})
    topics = _make_topics()
    task = _ConcreteTask(device, topics, step_name="test_step", do_task_fn=lambda: task.notify(_disconnect(device)))

    task.run()

    event = topics.info_progress.publish.call_args[0][0]
    assert event.success is False
    assert event.aborted is True


def test_run_reports_not_aborted_on_plain_failure():
    device = _make_device(pending={"test_step"})
    topics = _make_topics()
    task = _ConcreteTask(device, topics, step_name="test_step")

    task.run()

    assert topics.info_progress.publish.call_args[0][0].aborted is False
