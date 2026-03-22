"""Device discovery across all connection types.

Finds keyboard and mouse by scanning:
  1. Bolt / Unifying receivers — one HID device, multiple Logitech devices in slots 1-6
  2. Bluetooth — one HID device per Logitech device

Creates one listener thread per HID path. All listeners share a ProductRegistry
so host-switch events reach every known device regardless of connection type.
"""

from __future__ import annotations

import logging
import threading
import time

from .config import Config
from .event.divert_event import DivertEvent
from .gateway.hid_gateway import HidGateway
from .hidpp.constants import FEATURE_REPROG_CONTROLS_V4
from .hidpp.transport import enumerate_hid_devices
from .listener.bluetooth_listener import BluetoothListener
from .listener.receiver_listener import ReceiverListener
from .registry.logi_device_registry import LogiDeviceRegistry
from .setup.subscribers_setup import init_subscribers
from .topic.topic import Topic

log = logging.getLogger(__name__)


def discover(config: Config, shutdown: threading.Event) -> None:
    log.info("Starting device discovery…")
    log.info("Start pressing Easy-Switch buttons once at least 2 devices are discovered.")

    gateways: dict[int, list[HidGateway]] = {}
    device_registry = LogiDeviceRegistry()

    topics: dict[str, Topic] = {
        "event_topic": Topic(),
        "write_topic": Topic(),
        "device_info_topic": Topic(),
        "divert_topic": Topic(),
    }

    init_subscribers(topics, device_registry)

    try:
        while not shutdown.is_set():
            devices = enumerate_hid_devices(verbose_extra=config.arguments_settings.verbose_extra)
            # for device in devices:
            #     if device.pid not in gateways:
            #         event_listener = ReceiverListener(device, topics) if device.connection_type == "receiver" else BluetoothListener(device, topics)
            #         hid_gateway = HidGateway(device, event_listener, send_event_on_connection=device.connection_type == "bluetooth")
            #         topics["write_topic"].subscribe(hid_gateway)
            #         gateways[device.pid] = hid_gateway
            #         hid_gateway.start()
            #         event_listener.start()

            for pid, collections in devices.items():
                if pid not in gateways:
                    device = collections[0]
                    event_listener = ReceiverListener(device, topics) if device.connection_type == "receiver" else BluetoothListener(device, topics)
                    for collection in collections:
                        hid_gateway = HidGateway(collection, event_listener, send_event_on_connection=collection.connection_type == "bluetooth")
                        topics["write_topic"].subscribe(hid_gateway)
                        pid_gateways = gateways.get(pid, list())
                        pid_gateways.append(hid_gateway)
                        gateways[device.pid] = pid_gateways
                        hid_gateway.start()
                    event_listener.start()

            shutdown.wait(0.5)
        _undivert_all(device_registry, topics)
        for gates in gateways.values():
            for gateway in gates:
                gateway.close()

    except RuntimeError as error:
        log.error(f"Error occurred running discovery: {error}")


def _undivert_all(device_registry: LogiDeviceRegistry, topics: dict[str, Topic]) -> None:
    for device in device_registry.all_entries():
        if not device.divertable_cids:
            continue
        if device.available_features.get(FEATURE_REPROG_CONTROLS_V4) is None:
            continue
        topics["divert_topic"].publish(DivertEvent(
            slot=device.slot,
            pid=device.pid,
            wpid=device.wpid,
            cids=device.divertable_cids,
            divert=False,
        ))
    time.sleep(0.1)
