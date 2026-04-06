"""Device discovery across all connection types.

Finds keyboard and mouse by scanning:
  1. Bolt / Unifying receivers — one HID device, multiple Logitech devices in slots 1-6
  2. Bluetooth — one HID device per Logitech device

Creates one listener thread per HID path. All listeners share a ProductRegistry
so host-switch events reach every known device regardless of connection type.
"""

from __future__ import annotations

import logging
import time

from ..connection.trigger.receiver_trigger import ReceiverConnectionTrigger
from ..connection.trigger.receiver_trigger_mac import ReceiverConnectionTriggerMac
from ..event.divert_event import DivertEvent
from ..gateway.hid_gateway import HidGateway
from ..gateway.hid_gateway_bt import HidGatewayBT
from ..hidpp.constants import FEATURE_REPROG_CONTROLS_V4
from ..hidpp.transport import enumerate_hid_devices
from ..listener.event_listener import EventListener
from ..model.context.app_context import AppContext
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..topic.topics import Topics
from ..util.util import get_system

log = logging.getLogger(__name__)


def discover(app_context: AppContext) -> None:
    log.info("Starting device discovery…")

    gateways: dict[int, list[HidGateway]] = {}

    topics: Topics = app_context.topics
    shutdown = app_context.shutdown

    try:
        while not shutdown.is_set():
            devices = enumerate_hid_devices(verbose_extra=app_context.config.arguments_settings.verbose_extra)

            for pid, collections in devices.items():
                if pid not in gateways:
                    device = collections[0]
                    if device.connection_type == "receiver":
                        if get_system() == "Darwin":
                            connection_trigger = ReceiverConnectionTriggerMac(device, topics)
                        else:
                            connection_trigger = ReceiverConnectionTrigger(device, topics)
                    else:
                        connection_trigger = None
                    event_listener = EventListener(device, topics, connection_trigger)
                    for collection in collections:
                        hid_gateway = (
                            HidGateway(collection, event_listener)
                            if device.connection_type == "receiver"
                            else HidGatewayBT(collection, event_listener)
                        )
                        topics.write.subscribe(hid_gateway)
                        pid_gateways = gateways.get(pid, list())
                        pid_gateways.append(hid_gateway)
                        gateways[device.pid] = pid_gateways
                        hid_gateway.start()
                    event_listener.start()

            shutdown.wait(0.5)
        _undivert_all(app_context.device_registry, topics)
        for gates in gateways.values():
            for gateway in gates:
                gateway.close()

    except RuntimeError as error:
        log.error(f"Error occurred running discovery: {error}")


def _undivert_all(device_registry: LogiDeviceRegistry, topics: Topics) -> None:
    for device in device_registry.all_entries():
        if not device.divertable_cids:
            continue
        if device.available_features.get(FEATURE_REPROG_CONTROLS_V4) is None:
            continue
        topics.divert.publish(
            DivertEvent(
                slot=device.slot,
                pid=device.pid,
                wpid=device.wpid,
                cids=device.divertable_cids,
                divert=False,
            )
        )
    time.sleep(0.1)
