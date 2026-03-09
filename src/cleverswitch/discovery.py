"""Device discovery across all connection types.

Finds keyboard and mouse by scanning:
  1. Bolt / Unifying receivers — reads pairing register to get wpid for each slot
  2. Bluetooth — enumerates HID devices by Bluetooth product ID

Transport handles are cached and reused across iterations to avoid
re-opening the same device (which fails on macOS with exclusive access
and leaks file descriptors on all platforms).
"""

from __future__ import annotations

import logging
import threading

from .hidpp.transport import enumerate_hid_devices
from .listeners import PathListener

log = logging.getLogger(__name__)


def discover(shutdown: threading.Event) -> None:
    log.info("Starting device discovery…")

    listeners: dict[bytes, PathListener] = {}

    try:
        while not shutdown.is_set():
            devices = enumerate_hid_devices()

            # Remove listeners for paths that disappeared
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
                    listener = PathListener(device, shutdown)
                    listeners[device.path] = listener
                    listener.start()

            shutdown.wait(0.5)
    except RuntimeError as error:
        log.error(f"Error occurred running discovery: {error}")
    finally:
        for listener in listeners.values():
            listener.join(0.5)
