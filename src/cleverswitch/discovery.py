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
from .hidpp.transport import enumerate_hid_devices
from .gateway.hid_gateway import HidGateway
from .listener.bluetooth_listener import BluetoothListener
from .listener.receiver_listener import ReceiverListener
from .registry.logi_device_registry import LogiDeviceRegistry
from .event.divert_event import DivertEvent
from .hidpp.constants import FEATURE_REPROG_CONTROLS_V4
from .subscriber.device_connected_subscriber import DeviceConnectinSubscriber
from .subscriber.device_info_subscriber import DeviceInfoSubscriber
from .subscriber.divert_subscriber import DivertSubscriber
from .subscriber.diverted_host_change_subscriber import DivertedHostChangeSubscriber
from .subscriber.external_undivert_subscriber import ExternalUndivertSubscriber
from .subscriber.host_change_subscriber import HostChangeSubscriber
from .topic.topic import Topic

log = logging.getLogger(__name__)


def discover(config: Config, shutdown: threading.Event) -> None:
    log.info("Starting device discovery…")
    log.info("Start pressing Easy-Switch buttons once at least 2 devices are discovered.")

    # registry = ProductRegistry()
    # listeners: dict[bytes, BaseListener] = {}
    readers: dict[int, HidGateway] = {}
    device_registry = LogiDeviceRegistry()

    topics: dict[str, Topic] = {
        "event_topic": Topic(),
        "write_topic": Topic(),
        "device_info_topic": Topic(),
        "divert_topic": Topic(),
    }

    device_info_subscriber = DeviceInfoSubscriber(device_registry, topics)

    topics["event_topic"].subscribe(DeviceConnectinSubscriber(device_registry, topics))
    topics["event_topic"].subscribe(device_info_subscriber)
    topics["device_info_topic"].subscribe(device_info_subscriber)
    topics["divert_topic"].subscribe(DivertSubscriber(device_registry, topics))
    topics["event_topic"].subscribe(ExternalUndivertSubscriber(device_registry, topics))
    topics["event_topic"].subscribe(HostChangeSubscriber(device_registry, topics))
    topics["event_topic"].subscribe(DivertedHostChangeSubscriber(device_registry, topics))

    try:
        while not shutdown.is_set():
            devices = enumerate_hid_devices(verbose_extra=config.arguments_settings.verbose_extra)

            # Remove listeners for paths that disappeared or threads that died
            # current_paths = {d.path for d in devices}
            # removed_paths = set()
            # for path, listener in listeners.items():
            #     if path not in current_paths:
            #         removed_paths.add(path)
            #     if not listener.is_alive():
            #         removed_paths.add(path)
            #
            # for path in removed_paths:
            #     listeners.pop(path).stop()

            # Add listeners for new paths
            for device in devices:
                if device.pid not in readers:
                    event_listener = ReceiverListener(device, topics) if device.connection_type == "receiver" else BluetoothListener(device, topics)
                    hid_gateway = HidGateway(device, event_listener)
                    topics["write_topic"].subscribe(hid_gateway)
                    readers[device.pid] = hid_gateway
                    hid_gateway.start()
                    event_listener.start()

            shutdown.wait(0.5)
        _undivert_all(device_registry, topics)
        for reader in readers.values():
            reader.close()
    except RuntimeError as error:
        log.error(f"Error occurred running discovery: {error}")
    # finally:
    #     for listener in listeners.values():
    #         listener.join(0.5)


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
