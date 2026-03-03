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
    """Background discovery loop. Runs until *shutdown* is set.

    Caches transport handles and DeviceContexts across iterations so we
    don't re-open devices every second. Evicts stale entries when a device
    disappears from OS enumeration.
    """
    log.info("Starting device discovery…")

    listeners: list[PathListener] = []
    known_paths = {}

    try:
        while not shutdown.is_set():
            devices = enumerate_hid_devices()

            if known_paths != devices:
                for device in devices:
                    listener = PathListener(device, shutdown)
                    listeners.append(listener)
                    listener.start()
                known_paths = devices

            shutdown.wait(5)
    except RuntimeError as error:
        log.error(f"Error occurred running discovery: {error}")
    finally:
        for listener in listeners:
            listener.join(0.5)
