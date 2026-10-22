"""Device discovery across all connection types.

Finds keyboard and mouse by scanning:
  1. Bolt / Unifying receivers — one HID device, multiple Logitech devices in slots 1-6
  2. Bluetooth — one HID device per Logitech device

Creates one DeviceLink per HID product id (see link_factory.py), which owns a gateway
thread per HID collection and the pid's EventListener.
"""

from __future__ import annotations

import logging
import time

from ..event.set_report_flag_event import SetReportFlagEvent
from ..gateway.device_link import DeviceLink
from ..hidpp.constants import FEATURE_REPROG_CONTROLS_V4, KEY_FLAG_ANALYTICS
from ..hidpp.transport import enumerate_hid_devices
from ..model.context.app_context import AppContext
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..topic.topics import Topics
from .link_factory import create_link

log = logging.getLogger(__name__)


def discover(app_context: AppContext) -> None:
    log.info("Starting device discovery…")

    links: dict[int, DeviceLink] = {}

    topics: Topics = app_context.topics
    shutdown = app_context.shutdown

    try:
        while not shutdown.is_set():
            devices = enumerate_hid_devices(verbose_extra=app_context.config.arguments_settings.verbose_extra)

            for pid, collections in devices.items():
                if pid not in links:
                    link = create_link(pid, collections, topics)
                    links[pid] = link
                    link.start()

            shutdown.wait(0.5)
        _undivert_all(app_context.device_registry, topics)
        for link in links.values():
            link.close()

    except RuntimeError as error:
        log.error(f"Error occurred running discovery: {error}")


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
