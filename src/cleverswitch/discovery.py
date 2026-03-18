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

from .config import Config
from .hidpp.transport import enumerate_hid_devices
from .listeners import BaseListener, BTListener, ProductRegistry, ReceiverListener
from .reader.hid_reader import HidReader

log = logging.getLogger(__name__)


def discover(config: Config, shutdown: threading.Event) -> None:
    log.info("Starting device discovery…")
    log.info("Start pressing Easy-Switch buttons once at least 2 devices are discovered.")

    registry = ProductRegistry()
    listeners: dict[bytes, BaseListener] = {}
    readers: dict[int, HidReader] = {}

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
                    hid_reader = HidReader(device)
                    readers[device.pid] = hid_reader
                    hid_reader.start()

            shutdown.wait(0.5)
        for reader in readers.values():
            reader.close()
    except RuntimeError as error:
        log.error(f"Error occurred running discovery: {error}")
    finally:
        for listener in listeners.values():
            listener.join(0.5)
