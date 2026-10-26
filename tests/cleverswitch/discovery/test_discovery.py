"""Unit tests for discovery.py — background device discovery loop."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

from cleverswitch.discovery.discovery import _undivert_all, discover
from cleverswitch.event.set_report_flag_event import SetReportFlagEvent
from cleverswitch.hidpp.constants import (
    BOLT_PID,
    CONNECTION_RECEIVER,
    FEATURE_CHANGE_HOST,
    FEATURE_REPROG_CONTROLS_V4,
    KEY_FLAG_ANALYTICS,
)
from cleverswitch.model.context.app_context import AppContext
from cleverswitch.model.logi_device import LogiDevice
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


def test_discover_returns_immediately_when_shutdown_is_already_set(mocker):
    mocker.patch("cleverswitch.discovery.discovery.enumerate_hid_devices", return_value={})
    shutdown = threading.Event()
    shutdown.set()
    ctx = _make_app_context(shutdown=shutdown)
    discover(ctx)  # must return without hanging


def _receiver_device():
    from cleverswitch.hidpp.transport import HidDeviceInfo

    return HidDeviceInfo(
        path=b"/dev/hidraw0",
        vid=0x046D,
        pid=BOLT_PID,
        usage_page=0xFF00,
        usage=0x0002,
        connection_type=CONNECTION_RECEIVER,
    )


def _stop_after(shutdown, waits=1):
    count = [0]

    def fake_wait(timeout):
        count[0] += 1
        if count[0] >= waits:
            shutdown.set()

    shutdown.wait = fake_wait


def test_discover_creates_and_starts_a_link_per_pid(mocker):
    device = _receiver_device()
    mocker.patch("cleverswitch.discovery.discovery.enumerate_hid_devices", return_value={BOLT_PID: [device]})
    create_link = mocker.patch("cleverswitch.discovery.discovery.create_link")
    shutdown = threading.Event()
    _stop_after(shutdown)

    ctx = _make_app_context(shutdown=shutdown)
    discover(ctx)

    create_link.assert_called_once_with(BOLT_PID, [device], ctx.topics)
    create_link.return_value.start.assert_called_once()


def test_discover_does_not_create_duplicate_links_for_same_pid(mocker):
    mocker.patch(
        "cleverswitch.discovery.discovery.enumerate_hid_devices", return_value={BOLT_PID: [_receiver_device()]}
    )
    create_link = mocker.patch("cleverswitch.discovery.discovery.create_link")
    shutdown = threading.Event()
    _stop_after(shutdown, waits=2)

    discover(_make_app_context(shutdown=shutdown))

    assert create_link.call_count == 1


def test_discover_closes_links_on_shutdown(mocker):
    mocker.patch(
        "cleverswitch.discovery.discovery.enumerate_hid_devices", return_value={BOLT_PID: [_receiver_device()]}
    )
    create_link = mocker.patch("cleverswitch.discovery.discovery.create_link")
    shutdown = threading.Event()
    _stop_after(shutdown)

    discover(_make_app_context(shutdown=shutdown))

    create_link.return_value.close.assert_called_once()


# ── _undivert_all ─────────────────────────────────────────────────────────────


def test_undivert_all_publishes_set_report_flag_event_with_enable_false(mocker):
    mocker.patch("cleverswitch.discovery.discovery.time.sleep")
    registry = LogiDeviceRegistry()
    device = LogiDevice(
        wpid=0x407B,
        pid=BOLT_PID,
        slot=1,
        role="keyboard",
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
        role="mouse",
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
        role="keyboard",
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
