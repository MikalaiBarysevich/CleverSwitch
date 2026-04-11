"""Unit tests for subscriber/info_task_orchestrator.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cleverswitch.event.info_task_progress_event import InfoTaskProgressEvent
from cleverswitch.hidpp.constants import BOLT_PID
from cleverswitch.model.logi_device import LogiDevice
from cleverswitch.subscriber.info_task_orchestrator import InfoTaskOrchestrator
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics

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


def _progress(device, step_name="resolve_reprog", success=True):
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


def test_retries_immediately_when_device_connected():
    device = _make_device(pending={"resolve_reprog"}, connected=True)
    orch, topics, _ = _make_orchestrator()

    with patch("cleverswitch.subscriber.info_task_orchestrator._TASK_FACTORIES") as mock_factories:
        mock_task = MagicMock()
        mock_factories.__getitem__ = MagicMock(return_value=MagicMock(return_value=mock_task))
        orch.notify(_progress(device, step_name="resolve_reprog", success=False))
        mock_task.start.assert_called_once()


def test_no_retry_when_device_disconnected():
    device = _make_device(pending={"resolve_reprog"}, connected=False)
    orch, topics, _ = _make_orchestrator()

    with patch("cleverswitch.subscriber.info_task_orchestrator._TASK_FACTORIES") as mock_factories:
        mock_task = MagicMock()
        mock_factories.__getitem__ = MagicMock(return_value=MagicMock(return_value=mock_task))
        orch.notify(_progress(device, step_name="resolve_reprog", success=False))
        mock_task.start.assert_not_called()


def test_logs_fully_discovered_only_once_per_device(caplog):
    device = _make_device(pending=set())
    orch, topics, _ = _make_orchestrator()

    import logging
    with caplog.at_level(logging.INFO):
        orch.notify(_progress(device, step_name="get_device_name", success=True))
        orch.notify(_progress(device, step_name="get_device_type", success=True))

    assert caplog.text.lower().count("fully discovered") == 1


def test_ignores_non_progress_events():
    orch, topics, _ = _make_orchestrator()
    orch.notify("not an event")  # must not raise
