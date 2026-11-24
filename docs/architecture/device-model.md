# Device model and cache

## LogiDevice state

`model/logi_device.py` — mutable dataclass tracking:
- `available_features: dict[int, int]` — feature code → feature index (populated by feature tasks)
- `pending_steps: set[str]` — setup steps not yet completed
- `supported_flags: set[int]` — ES key capability flags (KEY_FLAG_DIVERTABLE, KEY_FLAG_PERSISTENTLY_DIVERTABLE, KEY_FLAG_ANALYTICS); populated by `FindESCidsFlagsTask` and mutated at runtime by `AnalyticsRejectionSubscriber` (drops `KEY_FLAG_ANALYTICS` on silent rejection); all ES CIDs share the same flags so this is per-device, not per-CID
- `connected: bool` — current connection state (gates orchestrator retries)
- `role`, `name`, `friendly_name` — populated during setup; `name` is the marketing string from feature 0x0005 (e.g. "Wireless Keyboard MX Keys"), `friendly_name` is the short label from feature 0x0007 (e.g. "MX Keys")
- `display_name` property — returns `friendly_name or name`. **All log lines and hook calls must label devices via `device.display_name`, never `device.name` directly**, so the short label is preferred wherever it's available

## Device cache

`DeviceCache` (`cache/device_cache.py`) persists discovered devices to a JSON file so a known device skips HID++ discovery on the next launch. It wraps its own `LogiDeviceRegistry`; entries are whole `LogiDevice` objects serialized via a `DiskCache` dataclass (`model/disk_cache.py`) — `{version, devices: [...]}`, a list keyed internally by wpid.

- **Path**: `config.cache_path`, from config key `cache.path`; defaults to `~/.config/cleverswitch/device_cache.json`. `--clear-cache` deletes the file and exits without starting the daemon.
- **Never crashes startup**: `load()` degrades to empty on any read failure (missing/corrupt file, wrong `version`, malformed `devices`), and skips individual malformed entries.
- **Repairs a cached keyboard without 0x1B04**: `load()` re-adds `CID_REPORTING` + `FIND_ES_CIDS_FLAGS` to its `pending_steps`, so the reconnection path rediscovers them. `DeviceConnectionSubscriber` and `ChannelRearmSubscriber` log a WARNING if they still find a keyboard without 0x1B04 and no pending CID step.
- **Fits the existing architecture — no new event or topic.** `setup_context()` builds the cache (loaded once) and injects it into `DeviceConnectionSubscriber`, `InfoTaskOrchestrator`, `AnalyticsRejectionSubscriber`, and `EventHookSubscriber`.
  - Read on connect: `DeviceConnectionSubscriber` registers a cache-hit device and runs the reconnection path — arming flags and requesting info only for still-pending steps (so a partially-cached device fetches just the gaps).
  - Written by `InfoTaskOrchestrator.save` on full discovery, and by `AnalyticsRejectionSubscriber` when it drops `KEY_FLAG_ANALYTICS`.
- `save()` writes the whole file atomically (temp file + `os.replace`) and swallows write errors (logs a warning; in-memory entry still updates).
