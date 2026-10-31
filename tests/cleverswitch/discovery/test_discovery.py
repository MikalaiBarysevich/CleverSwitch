"""Unit tests for discovery.py — background device discovery loop."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest

from cleverswitch.discovery.discovery import _undivert_all, discover
from cleverswitch.errors.errors import HotplugError
from cleverswitch.event.hotplug_resync_event import HotplugResyncEvent
from cleverswitch.event.set_report_flag_event import SetReportFlagEvent
from cleverswitch.hidpp.constants import (
    BOLT_PID,
    FEATURE_CHANGE_HOST,
    FEATURE_REPROG_CONTROLS_V4,
    KEY_FLAG_ANALYTICS,
)
from cleverswitch.model.context.app_context import AppContext
from cleverswitch.model.logi_device import ROLE_KEYBOARD, ROLE_MOUSE, LogiDevice
from cleverswitch.registry.logi_device_registry import LogiDeviceRegistry
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics


def _make_app_context(shutdown=None, registry=None, topics=None):
    if shutdown is None:
        shutdown = threading.Event()
    if registry is None:
        registry = LogiDeviceRegistry()
    if topics is None:
        topics = Topics(
            hid_event=MagicMock(spec=Topic),
            write=MagicMock(spec=Topic),
            device_info=MagicMock(spec=Topic),
            flags=MagicMock(spec=Topic),
            info_progress=MagicMock(spec=Topic),
        )
    config = MagicMock()
    config.arguments_settings.verbose_extra = False
    return AppContext(device_registry=registry, topics=topics, config=config, shutdown=shutdown)


def _patch_wiring(mocker):
    manager_cls = mocker.patch("cleverswitch.discovery.discovery.LinkManager")
    create_backend = mocker.patch("cleverswitch.discovery.discovery.create_backend")
    undivert = mocker.patch("cleverswitch.discovery.discovery._undivert_all")
    order = MagicMock()
    order.attach_mock(create_backend.return_value.start, "backend_start")
    order.attach_mock(create_backend.return_value.stop, "backend_stop")
    order.attach_mock(undivert, "undivert")
    order.attach_mock(manager_cls.return_value.close_all, "close_all")
    return manager_cls, create_backend, undivert, order


def _stopped_context():
    shutdown = threading.Event()
    shutdown.set()
    return _make_app_context(shutdown=shutdown)


def test_discover_builds_the_link_manager_on_the_hotplug_topic(mocker):
    manager_cls, _, _, _ = _patch_wiring(mocker)
    ctx = _stopped_context()

    discover(ctx)

    manager_cls.assert_called_once_with(ctx.topics, verbose_extra=False)


def test_discover_resyncs_after_the_backend_is_registered(mocker):
    _, create_backend, _, _ = _patch_wiring(mocker)
    ctx = _stopped_context()
    ctx.topics.hotplug = MagicMock(spec=Topic)
    ctx.topics.hotplug.publish.side_effect = lambda _e: create_backend.return_value.start.assert_called_once()

    discover(ctx)

    create_backend.assert_called_once_with(ctx.topics)
    ctx.topics.hotplug.publish.assert_called_once_with(HotplugResyncEvent(slot=0, pid=0))


def test_discover_tears_down_in_order_on_shutdown(mocker):
    _, _, _, order = _patch_wiring(mocker)

    discover(_stopped_context())

    assert [c[0] for c in order.mock_calls] == ["backend_start", "backend_stop", "undivert", "close_all"]


def test_discover_waits_for_shutdown(mocker):
    _patch_wiring(mocker)
    ctx = _make_app_context()
    worker = threading.Thread(target=discover, args=(ctx,), daemon=True)
    worker.start()
    worker.join(timeout=0.2)
    assert worker.is_alive()

    ctx.shutdown.set()
    worker.join(timeout=2.0)

    assert not worker.is_alive()


def test_discover_propagates_a_backend_that_cannot_start(mocker):
    manager_cls, create_backend, undivert, _ = _patch_wiring(mocker)
    create_backend.return_value.start.side_effect = HotplugError("no netlink")
    ctx = _stopped_context()
    ctx.topics.hotplug = MagicMock(spec=Topic)

    with pytest.raises(HotplugError):
        discover(ctx)

    ctx.topics.hotplug.publish.assert_not_called()
    undivert.assert_not_called()


# ── _undivert_all ─────────────────────────────────────────────────────────────


def test_undivert_all_publishes_set_report_flag_event_with_enable_false(mocker):
    mocker.patch("cleverswitch.discovery.discovery.time.sleep")
    registry = LogiDeviceRegistry()
    device = LogiDevice(
        wpid=0x407B,
        pid=BOLT_PID,
        slot=1,
        role=ROLE_KEYBOARD,
        available_features={FEATURE_REPROG_CONTROLS_V4: 8, FEATURE_CHANGE_HOST: 9},
    )
    registry.register(0x407B, device)
    divert_topic = MagicMock()
    topics = Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        flags=divert_topic,
        info_progress=MagicMock(spec=Topic),
    )

    _undivert_all(registry, topics)

    divert_topic.publish.assert_called_once()
    event = divert_topic.publish.call_args[0][0]
    assert isinstance(event, SetReportFlagEvent)
    assert event.enable is False


def test_undivert_all_skips_device_without_reprog_feature(mocker):
    mocker.patch("cleverswitch.discovery.discovery.time.sleep")
    registry = LogiDeviceRegistry()
    device = LogiDevice(
        wpid=0x407B,
        pid=BOLT_PID,
        slot=2,
        role=ROLE_MOUSE,
        available_features={FEATURE_CHANGE_HOST: 9},
    )
    registry.register(0x407B, device)
    divert_topic = MagicMock()
    topics = Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        flags=divert_topic,
        info_progress=MagicMock(spec=Topic),
    )

    _undivert_all(registry, topics)

    divert_topic.publish.assert_not_called()


def test_undivert_all_skips_device_with_analytics_flag(mocker):
    mocker.patch("cleverswitch.discovery.discovery.time.sleep")
    registry = LogiDeviceRegistry()
    device = LogiDevice(
        wpid=0x407B,
        pid=BOLT_PID,
        slot=1,
        role=ROLE_KEYBOARD,
        available_features={FEATURE_REPROG_CONTROLS_V4: 8, FEATURE_CHANGE_HOST: 9},
    )
    device.supported_flags = {KEY_FLAG_ANALYTICS}
    registry.register(0x407B, device)
    divert_topic = MagicMock()
    topics = Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        flags=divert_topic,
        info_progress=MagicMock(spec=Topic),
    )

    _undivert_all(registry, topics)

    divert_topic.publish.assert_not_called()
