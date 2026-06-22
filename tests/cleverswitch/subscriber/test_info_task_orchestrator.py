"""Unit tests for subscriber/info_task_orchestrator.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.cleverswitch.event.info_task_progress_event import InfoTaskProgressEvent
from src.cleverswitch.hidpp.constants import BOLT_PID
from src.cleverswitch.model.logi_device import LogiDevice
from src.cleverswitch.subscriber.info_task_orchestrator import InfoTaskOrchestrator
from src.cleverswitch.subscriber.task.constants import Task
from src.cleverswitch.topic.topic import Topic
from src.cleverswitch.topic.topics import Topics

PID = BOLT_PID
SLOT = 1


def _make_device(pending=None, connected=True):
    d = LogiDevice(wpid=0x407B, pid=PID, slot=SLOT, role=None, available_features={})
    d.connected = connected
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


def _make_orchestrator(topics=None, registry=None):
    if topics is None:
        topics = _make_topics()
    if registry is None:
        registry = MagicMock()
    return InfoTaskOrchestrator(registry, topics), topics, registry


def _progress(device, step_name=Task.Feature.Name.CID_REPORTING, success=True):
    return InfoTaskProgressEvent(slot=device.slot, pid=device.pid, step_name=step_name, success=success, device=device)


def test_logs_fully_discovered_when_no_pending_on_success(caplog):
    device = _make_device(pending=set())
    orch, topics, _ = _make_orchestrator()

    import logging

    with caplog.at_level(logging.INFO):
        orch.notify(_progress(device, success=True))

    assert "fully discovered" in caplog.text.lower()


def test_no_log_when_pending_steps_remain_on_success(caplog):
    device = _make_device(pending={"other_step"})
    orch, topics, _ = _make_orchestrator()

    import logging

    with caplog.at_level(logging.INFO):
        orch.notify(_progress(device, success=True))

    assert "fully discovered" not in caplog.text.lower()


def test_schedules_backoff_timer_when_device_connected():
    device = _make_device(pending={Task.Feature.Name.CID_REPORTING}, connected=True)
    orch, topics, _ = _make_orchestrator()

    with patch("src.cleverswitch.subscriber.info_task_orchestrator.threading.Timer") as mock_timer_cls:
        orch.notify(_progress(device, step_name=Task.Feature.Name.CID_REPORTING, success=False))

        mock_timer_cls.assert_called_once()
        args, kwargs = mock_timer_cls.call_args
        assert args[0] == 0.5  # first retry uses base delay
        mock_timer_cls.return_value.start.assert_called_once()
        assert mock_timer_cls.return_value.daemon is True


def test_no_retry_scheduled_when_device_disconnected():
    device = _make_device(pending={Task.Feature.Name.CID_REPORTING}, connected=False)
    orch, topics, _ = _make_orchestrator()

    with patch("src.cleverswitch.subscriber.info_task_orchestrator.threading.Timer") as mock_timer_cls:
        orch.notify(_progress(device, step_name=Task.Feature.Name.CID_REPORTING, success=False))
        mock_timer_cls.assert_not_called()


def test_backoff_delay_doubles_each_attempt_and_caps():
    device = _make_device(pending={Task.Feature.Name.CID_REPORTING}, connected=True)
    orch, topics, _ = _make_orchestrator()

    delays = []
    with patch("src.cleverswitch.subscriber.info_task_orchestrator.threading.Timer") as mock_timer_cls:
        for _ in range(5):
            orch.notify(_progress(device, step_name=Task.Feature.Name.CID_REPORTING, success=False))
            delays.append(mock_timer_cls.call_args[0][0])

    assert delays == [0.5, 1.0, 2.0, 4.0, 8.0]


def test_gives_up_after_max_attempts(caplog):
    import logging

    device = _make_device(pending={Task.Feature.Name.CID_REPORTING}, connected=True)
    orch, topics, _ = _make_orchestrator()

    with patch("src.cleverswitch.subscriber.info_task_orchestrator.threading.Timer") as mock_timer_cls:
        for _ in range(5):
            orch.notify(_progress(device, step_name=Task.Feature.Name.CID_REPORTING, success=False))
        assert mock_timer_cls.call_count == 5

        with caplog.at_level(logging.WARNING):
            orch.notify(_progress(device, step_name=Task.Feature.Name.CID_REPORTING, success=False))

        assert mock_timer_cls.call_count == 5  # no further timer scheduled
        assert "giving up" in caplog.text.lower()


def test_success_resets_retry_attempts():
    device = _make_device(pending={Task.Feature.Name.CID_REPORTING}, connected=True)
    orch, topics, _ = _make_orchestrator()

    with patch("src.cleverswitch.subscriber.info_task_orchestrator.threading.Timer") as mock_timer_cls:
        orch.notify(_progress(device, step_name=Task.Feature.Name.CID_REPORTING, success=False))
        assert mock_timer_cls.call_args[0][0] == 0.5

        # a success on the same step clears the counter
        device.pending_steps = {Task.Feature.Name.CID_REPORTING}
        orch.notify(_progress(device, step_name=Task.Feature.Name.CID_REPORTING, success=True))

        orch.notify(_progress(device, step_name=Task.Feature.Name.CID_REPORTING, success=False))
        assert mock_timer_cls.call_args[0][0] == 0.5  # back to base delay


def test_fire_retry_creates_task_when_still_connected():
    device = _make_device(pending={Task.Feature.Name.CID_REPORTING}, connected=True)
    orch, topics, _ = _make_orchestrator()

    with patch("src.cleverswitch.subscriber.info_task_orchestrator._TASK_FACTORIES") as mock_factories:
        mock_task = MagicMock()
        mock_factories.__getitem__ = MagicMock(return_value=MagicMock(return_value=mock_task))
        orch._fire_retry(device, Task.Feature.Name.CID_REPORTING)
        mock_task.start.assert_called_once()


def test_fire_retry_skips_when_disconnected_meanwhile():
    device = _make_device(pending={Task.Feature.Name.CID_REPORTING}, connected=False)
    orch, topics, _ = _make_orchestrator()

    with patch("src.cleverswitch.subscriber.info_task_orchestrator._TASK_FACTORIES") as mock_factories:
        mock_task = MagicMock()
        mock_factories.__getitem__ = MagicMock(return_value=MagicMock(return_value=mock_task))
        orch._fire_retry(device, Task.Feature.Name.CID_REPORTING)
        mock_task.start.assert_not_called()


def test_logs_fully_discovered_only_once_per_device(caplog):
    device = _make_device(pending=set())
    orch, topics, _ = _make_orchestrator()

    import logging

    with caplog.at_level(logging.INFO):
        orch.notify(_progress(device, step_name=Task.Name.GET_DEVICE_NAME, success=True))
        orch.notify(_progress(device, step_name=Task.Name.GET_DEVICE_TYPE, success=True))

    assert caplog.text.lower().count("fully discovered") == 1


def test_ignores_non_progress_events():
    orch, topics, _ = _make_orchestrator()
    orch.notify("not an event")  # must not raise


def test_fallback_copy_sets_friendly_name_from_name_when_all_steps_done():
    device = _make_device(pending=set())
    device.name = "Wireless Keyboard MX Keys"
    device.friendly_name = None
    orch, topics, _ = _make_orchestrator()

    orch.notify(_progress(device, success=True))

    assert device.friendly_name == "Wireless Keyboard MX Keys"


def test_fallback_copy_does_not_overwrite_existing_friendly_name():
    device = _make_device(pending=set())
    device.name = "Wireless Keyboard MX Keys"
    device.friendly_name = "MX Keys"
    orch, topics, _ = _make_orchestrator()

    orch.notify(_progress(device, success=True))

    assert device.friendly_name == "MX Keys"


def test_fallback_copy_does_not_set_when_name_is_none():
    device = _make_device(pending=set())
    device.name = None
    device.friendly_name = None
    orch, topics, _ = _make_orchestrator()

    orch.notify(_progress(device, success=True))

    assert device.friendly_name is None
