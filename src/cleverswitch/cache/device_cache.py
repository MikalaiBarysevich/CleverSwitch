import json
import logging
import os
import threading
from pathlib import Path

from ..model.disk_cache import DiskCache
from ..model.logi_device import LogiDevice
from ..registry.logi_device_registry import LogiDeviceRegistry

log = logging.getLogger(__name__)

CACHE_VERSION = 1


class DeviceCache:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._cache_registry: LogiDeviceRegistry = LogiDeviceRegistry()

    def load(self) -> None:
        with self._lock:
            if not self._path.exists():
                log.debug(f"No device cache at {self._path}")
                return
            try:
                with open(self._path) as cache_path:
                    data = json.load(cache_path)
                disk_cache = DiskCache(**data)
            except (OSError, json.JSONDecodeError, TypeError) as e:
                log.warning(f"Could not read device cache {self._path}: {e}. Starting empty")
                return

            if disk_cache.version != CACHE_VERSION:
                log.warning(f"Ignoring device cache {self._path}: unsupported version. Starting empty")
                return

            if not isinstance(disk_cache.devices, list):
                log.warning(f"Ignoring device cache {self._path}: malformed devices. Starting empty")
                return

            for device_data in disk_cache.devices:
                try:
                    device = self._decode(device_data)
                except (KeyError, TypeError, AttributeError) as e:
                    log.warning(f"Skipping malformed device cache entry: {e}")
                    continue
                self._cache_registry.register(device.wpid, device)

    def find_by_wpid(self, wpid: int) -> LogiDevice | None:
        return self._cache_registry.get_by_wpid(wpid)

    def save(self, device: LogiDevice) -> None:
        with self._lock:
            self._cache_registry.register(device.wpid, device)
            self._write_to_disk()

    def clear(self) -> None:
        with self._lock:
            self._cache_registry = LogiDeviceRegistry()
            try:
                self._path.unlink(missing_ok=True)
                log.info(f"Cleared device cache at {self._path}")
            except OSError as e:
                log.warning(f"Failed to clear device cache {self._path}: {e}")

    def _write_to_disk(self) -> None:
        disk_cache = DiskCache(version=CACHE_VERSION, devices=self._cache_registry.all_entries())
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp, "w") as tmp_path:
                json.dump(disk_cache, tmp_path, indent=4, default=self._encode)
            os.replace(tmp, self._path)
            log.debug(f"Wrote device cache to {self._path}")
        except OSError as e:
            log.warning(f"Failed to write device cache {self._path}: {e}")

    def _encode(self, obj):
        if isinstance(obj, (set, frozenset)):
            return list(obj)
        try:
            return vars(obj)
        except TypeError as e:
            raise TypeError(f"Cannot serialize {type(obj).__name__}") from e

    def _decode(self, data: dict) -> LogiDevice:
        return LogiDevice(
            wpid=data["wpid"],
            pid=data["pid"],
            slot=data["slot"],
            role=data["role"],
            available_features={int(k): v for k, v in data["available_features"].items()},
            name=data.get("name"),
            friendly_name=data.get("friendly_name"),
            supported_flags=set(data.get("supported_flags", [])),
            pending_steps=set(data.get("pending_steps", [])),
            connected=data.get("connected", True),
        )
