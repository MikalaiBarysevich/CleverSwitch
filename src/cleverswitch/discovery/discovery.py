"""Device discovery across all connection types.

Finds receivers (Bolt / Unifying — several Logitech devices behind one HID device) and Bluetooth
devices (one HID device each) from OS hotplug notifications. LinkManager keeps one DeviceLink per
HID product id (see link_factory.py), which owns an HID channel thread per HID collection and the
pid's EventListener.
"""

from __future__ import annotations

import logging
import time

from ..event.hotplug_resync_event import HotplugResyncEvent
from ..event.set_report_flag_event import SetReportFlagEvent
from ..hidpp.constants import FEATURE_REPROG_CONTROLS_V4, KEY_FLAG_ANALYTICS
from ..hotplug.backend_factory import create_backend
from ..model.context.app_context import AppContext
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..topic.topics import Topics
from .link_manager import LinkManager

log = logging.getLogger(__name__)


def discover(app_context: AppContext) -> None:
    topics: Topics = app_context.topics
    manager = LinkManager(topics, verbose_extra=app_context.config.arguments_settings.verbose_extra)
    backend = create_backend(topics)
    backend.start()

    log.info("Starting device discovery…")
    try:
        topics.hotplug.publish(HotplugResyncEvent(slot=0, pid=0))
        app_context.shutdown.wait()
    finally:
        backend.stop()
        _undivert_all(app_context.device_registry, topics)
        manager.close_all()


def _undivert_all(device_registry: LogiDeviceRegistry, topics: Topics) -> None:
    for device in device_registry.all_entries():
        if KEY_FLAG_ANALYTICS in device.supported_flags:
            continue
        if device.available_features.get(FEATURE_REPROG_CONTROLS_V4) is None:
            continue
        topics.flags.publish(
            SetReportFlagEvent(
                slot=device.slot,
                pid=device.pid,
                wpid=device.wpid,
                enable=False,
            )
        )
    time.sleep(0.1)
