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

from .hidpp.transport import enumerate_hid_devices
from .listeners import BaseListener, BTListener, ProductRegistry, ReceiverListener

log = logging.getLogger(__name__)


def discover(shutdown: threading.Event) -> None:
    log.info("Starting device discovery…")

    registry = ProductRegistry()
    listeners: dict[bytes, BaseListener] = {}

    try:
        while not shutdown.is_set():
            devices = enumerate_hid_devices()

            # Remove listeners for paths that disappeared or threads that died
            current_paths = {d.path for d in devices}
            removed_paths = set()
            for path, listener in listeners.items():
                if path not in current_paths:
                    removed_paths.add(path)
                if not listener.is_alive():
                    removed_paths.add(path)

            for path in removed_paths:
                listeners.pop(path).stop()

            # Add listeners for new paths
            for device in devices:
                if device.path not in listeners:
                    if device.connection_type == "receiver":
                        listener = ReceiverListener(device, shutdown, registry)
                    else:
                        listener = BTListener(device, shutdown, registry)
                    listeners[device.path] = listener
                    listener.start()

            shutdown.wait(0.5)
    except RuntimeError as error:
        log.error(f"Error occurred running discovery: {error}")
    finally:
        for listener in listeners.values():
            listener.join(0.5)
