"""Unit tests for subscriber/info_task_orchestrator.py."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from src.cleverswitch.cache.device_cache import DeviceCache
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


def _make_orchestrator(topics=None, registry=None, cache=None):
    if topics is None:
        topics = _make_topics()
    if registry is None:
        registry = MagicMock()
    if cache is None:
        cache = MagicMock()
    return InfoTaskOrchestrator(registry, topics, cache), topics, registry, cache


def _progress(device, step_name=Task.Feature.Name.CID_REPORTING, success=True):
    return InfoTaskProgressEvent(slot=device.slot, pid=device.pid, step_name=step_name, success=success, device=device)


def test_logs_fully_discovered_when_no_pending_on_success(caplog):
    device = _make_device(pending=set())
    orch, topics, _, _ = _make_orchestrator()

    import logging

    with caplog.at_level(logging.INFO):
        orch.notify(_progress(device, success=True))

    assert "fully discovered" in caplog.text.lower()


def test_no_log_when_pending_steps_remain_on_success(caplog):
    device = _make_device(pending={"other_step"})
    orch, topics, _, _ = _make_orchestrator()

    import logging

    with caplog.at_level(logging.INFO):
        orch.notify(_progress(device, success=True))

    assert "fully discovered" not in caplog.text.lower()


def test_retries_immediately_when_device_connected():
    device = _make_device(pending={Task.Feature.Name.CID_REPORTING}, connected=True)
    orch, topics, _, _ = _make_orchestrator()

    with patch("src.cleverswitch.subscriber.info_task_orchestrator._TASK_FACTORIES") as mock_factories:
        mock_task = MagicMock()
        mock_factories.__getitem__ = MagicMock(return_value=MagicMock(return_value=mock_task))
        orch.notify(_progress(device, step_name=Task.Feature.Name.CID_REPORTING, success=False))
        mock_task.start.assert_called_once()


def test_no_retry_when_device_disconnected():
    device = _make_device(pending={Task.Feature.Name.CID_REPORTING}, connected=False)
    orch, topics, _, _ = _make_orchestrator()

    with patch("src.cleverswitch.subscriber.info_task_orchestrator._TASK_FACTORIES") as mock_factories:
        mock_task = MagicMock()
        mock_factories.__getitem__ = MagicMock(return_value=MagicMock(return_value=mock_task))
        orch.notify(_progress(device, step_name=Task.Feature.Name.CID_REPORTING, success=False))
        mock_task.start.assert_not_called()


def test_logs_fully_discovered_only_once_per_device(caplog):
    device = _make_device(pending=set())
    orch, topics, _, _ = _make_orchestrator()

    import logging

    with caplog.at_level(logging.INFO):
        orch.notify(_progress(device, step_name=Task.Name.GET_DEVICE_NAME, success=True))
        orch.notify(_progress(device, step_name=Task.Name.GET_DEVICE_TYPE, success=True))

    assert caplog.text.lower().count("fully discovered") == 1


def test_ignores_non_progress_events():
    orch, topics, _, _ = _make_orchestrator()
    orch.notify("not an event")  # must not raise


def test_saves_to_cache_once_on_full_discovery():
    device = _make_device(pending=set())
    orch, _, _, cache = _make_orchestrator()

    orch.notify(_progress(device, step_name=Task.Name.GET_DEVICE_NAME, success=True))
    orch.notify(_progress(device, step_name=Task.Name.GET_DEVICE_TYPE, success=True))

    cache.save.assert_called_once_with(device)


def test_does_not_save_when_steps_pending():
    device = _make_device(pending={"other_step"})
    orch, _, _, cache = _make_orchestrator()

    orch.notify(_progress(device, success=True))

    cache.save.assert_not_called()


def test_fallback_friendly_name_not_persisted(tmp_path):
    path = tmp_path / "cache.json"
    cache = DeviceCache(path)
    orch, _, _, _ = _make_orchestrator(cache=cache)

    device = _make_device(pending=set())
    device.name = "Wireless Mouse MX Master 3"
    device.friendly_name = None  # genuine friendly name never fetched (e.g. timed out)

    orch.notify(_progress(device, success=True))

    # runtime display still falls back to the marketing name
    assert device.friendly_name == "Wireless Mouse MX Master 3"
    # but the cache stores the genuine (null) value so it is re-fetched next launch
    devices = json.loads(path.read_text())["devices"]
    entry = next(e for e in devices if e["wpid"] == device.wpid)
    assert entry["friendly_name"] is None


def test_fallback_copy_sets_friendly_name_from_name_when_all_steps_done():
    device = _make_device(pending=set())
    device.name = "Wireless Keyboard MX Keys"
    device.friendly_name = None
    orch, topics, _, _ = _make_orchestrator()

    orch.notify(_progress(device, success=True))

    assert device.friendly_name == "Wireless Keyboard MX Keys"


def test_fallback_copy_does_not_overwrite_existing_friendly_name():
    device = _make_device(pending=set())
    device.name = "Wireless Keyboard MX Keys"
    device.friendly_name = "MX Keys"
    orch, topics, _, _ = _make_orchestrator()

    orch.notify(_progress(device, success=True))

    assert device.friendly_name == "MX Keys"


def test_fallback_copy_does_not_set_when_name_is_none():
    device = _make_device(pending=set())
    device.name = None
    device.friendly_name = None
    orch, topics, _, _ = _make_orchestrator()

    orch.notify(_progress(device, success=True))

    assert device.friendly_name is None
