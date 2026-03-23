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
from .hidpp.constants import HIDPP_USAGES_LONG, HIDPP_USAGES_SHORT
from .hidpp.transport import HidDeviceInfo, enumerate_hid_devices
from .listeners import BaseListener, BTListener, ProductRegistry, ReceiverListener
from .model import CachedBTDevice

log = logging.getLogger(__name__)


class BTDeviceCache:
    """Thread-safe in-memory cache of BT device identities, keyed by PID.

    Allows BTListener to skip the slow HID++ feature-discovery probe on reconnect
    by restoring the cached identity (role, name, feature indices) for a known PID.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: dict[int, CachedBTDevice] = {}

    def get(self, pid: int) -> CachedBTDevice | None:
        with self._lock:
            return self._cache.get(pid)

    def put(self, entry: CachedBTDevice) -> None:
        with self._lock:
            self._cache[entry.pid] = entry


def _find_short_device(long_device: HidDeviceInfo, all_devices: list[HidDeviceInfo]) -> HidDeviceInfo | None:
    """On Windows, find the SHORT-usage HID collection for the same receiver PID.

    The Bolt/Unifying receiver enumerates two HID collections on Windows:
    - Long collection  (usage 0x0002) — used for normal HID++ 2.0 traffic
    - Short collection (usage 0x0001) — delivers REPORT_SHORT disconnect notifications

    Returns the short-usage entry for the same PID, or None if not found or not
    on Windows (Linux/macOS use a single handle that receives all report types).
    """
    for device in all_devices:
        if device.pid == long_device.pid and device.usage in HIDPP_USAGES_SHORT:
            return device
    return None


def discover(config: Config, shutdown: threading.Event) -> None:
    log.info("Starting device discovery…")
    log.info("Start pressing Easy-Switch buttons once at least 2 devices are discovered.")

    preferred_host = config.settings.preferred_host if config is not None else None

    registry = ProductRegistry()
    bt_cache = BTDeviceCache()
    listeners: dict[bytes, BaseListener] = {}

    try:
        while not shutdown.is_set():
            devices = enumerate_hid_devices(verbose_extra=config.arguments_settings.verbose_extra)

            # Separate long-usage entries (used for listeners) from short-usage entries
            # (Windows-only short collection for disconnect notifications).
            long_devices = [d for d in devices if d.usage in HIDPP_USAGES_LONG]
            all_devices = devices

            # Remove listeners for paths that disappeared or threads that died
            current_paths = {d.path for d in long_devices}
            removed_paths = set()
            for path, listener in listeners.items():
                if path not in current_paths:
                    removed_paths.add(path)
                if not listener.is_alive():
                    removed_paths.add(path)

            for path in removed_paths:
                listeners.pop(path).stop()

            # Add listeners for new paths
            for device in long_devices:
                if device.path not in listeners:
                    if device.connection_type == "receiver":
                        short_device = _find_short_device(device, all_devices)
                        listener = ReceiverListener(
                            device,
                            shutdown,
                            registry,
                            preferred_host=preferred_host,
                            short_hid_device_info=short_device,
                        )
                    else:
                        listener = BTListener(device, shutdown, registry, bt_cache=bt_cache)
                    listeners[device.path] = listener
                    listener.start()

            shutdown.wait(0.5)
    except RuntimeError as error:
        log.error(f"Error occurred running discovery: {error}")
    finally:
        for listener in listeners.values():
            listener.join(0.5)
