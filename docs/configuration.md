# Configuration

CleverSwitch reads one optional YAML config file. Without it, built-in defaults are used: hooks and edge switch stay off, and logging uses its defaults.

## Location

- **Linux / macOS:** `~/.config/cleverswitch/config.yaml`
- **Windows:** `%USERPROFILE%\.config\cleverswitch\config.yaml`

Override the path with `--config FILE`. A missing file at the default path is fine; a missing file passed to `--config` is an error.

A starting point is provided in [`config.example.yaml`](../config.example.yaml) — copy it to the path above and rename it to `config.yaml`.

## When it is read

The file is read **once at startup**. Restart CleverSwitch after editing it, including changes to hooks, logging and `edge_switch`.

- Invalid YAML, a top level that is not a mapping, or a non-mapping `hooks`, `logging`, `logging.file` or `cache` section stops the daemon with an error.
- A malformed hook entry is logged and skipped; the rest of the config still loads.
- A bad `edge_switch` section is logged and can turn edge switch off: a non-mapping section, an invalid `modifier`, no valid `edges`, or a non-boolean `enabled` disable it. Unknown edges and keys are ignored, and an invalid `cooldown_ms` falls back to its default.
- Invalid `logging.level`, `file.max_size_mb` and `file.backup_count` values are logged and replaced with their defaults.

## Sections

| Section | Purpose | Reference |
|---|---|---|
| `hooks` | Run commands on switch, connect and disconnect events | [Hooks](features/hooks.md) |
| `logging` | Log level, file path, rotation | [Logging](features/logging.md) |
| `edge_switch` | Switch hosts by holding a modifier at a screen edge | [Edge switch](features/edge-switch.md) |
| `cache` | Where discovered device info is stored | [details below](#cache) |

### `cache`

Discovered device information is cached so a reconnect skips discovery. The cache is a JSON file at `~/.config/cleverswitch/device_cache.json` by default.

```yaml
cache:
  path: ~/.config/cleverswitch/device_cache.json
```

To reset it, run `cleverswitch --clear-cache`: the cache is deleted and the command exits without starting the daemon.

## CLI options

| Option | Description |
|---|---|
| `-c`, `--config FILE` | Use a specific config file |
| `-v`, `--verbose` | Force DEBUG logging |
| `-vv`, `--verbose-extra` | Force DEBUG logging including discovery |
| `--clear-cache` | Delete the discovered-device cache and exit |
| `--version` | Print the version, hidapi version and platform |

## Full reference

The annotated example covers every section and key:

- [`config.example.yaml`](../config.example.yaml)
- [Hooks](features/hooks.md) — events, environment variables, hook keys
- [Logging](features/logging.md) — level and rotation settings
- [Edge switch](features/edge-switch.md) — gesture, host mapping and platform requirements
