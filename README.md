# CleverSwitch

A small, headless, cross-platform daemon that synchronizes host switching between Logitech keyboard and mouse.
When you press the Easy-Switch button on the keyboard, CleverSwitch detects it and immediately sends the same host-switch command to the mouse — so both devices land on the same host simultaneously.

- Runs alongside Logi Options+ or Solaar without conflicts.
- Must be installed on every host you plan to switch from.
- Supports connections via Logitech receivers and Bluetooth.
- Tested with `MX Keys` and `MX Master 3` on Linux, macOS, and Windows.

> **Note:** CleverSwitch does not override device firmware. It acts as a forwarder, which means there is a small delay after reconnection. If you switch back immediately after arriving from another host, the devices may not switch together — CleverSwitch needs a moment to set everything up after reconnection.

## Support the Project

If you find this project useful, consider supporting its development:

- **Credit Card:** [Donate via Boosty](https://boosty.to/mikalaibarysevich)
- **Crypto:**
    - `BTC`: 1HXzgmGZHjLMWrQC8pgYvmcm6afD4idqr7
    - `USDT (TRC20)`: TXpJ3MHcSc144npXLuRbU81gJjD8cwAyzP

## Installation

See [installation guide](docs/Installation.md) for full installation, update, startup, and uninstall instructions for all platforms.


## Hook Scripts

Hook scripts let you run custom commands or scripts in response to CleverSwitch events. Hooks are executed asynchronously and never block the switch relay.
You should use this when you need some extra logic. Like switch display input source when devices connects to current PC.

By default, hooks only fire for keyboard events. Set `hooks.fire_for_all_devices: true` in config to include mouse events as well.

### Events

| Event        | When it fires                                                 |
|--------------|---------------------------------------------------------------|
| `switch`     | The Easy-Switch button was pressed, or an edge switch fired, and a host change was sent |
| `connect`    | A device connected (including wake from sleep)                |
| `disconnect` | A device disconnected (including sleep)                       |

### Environment variables

Each hook receives the following environment variables:

| Variable                   | Values                                | Description                                        |
|----------------------------|---------------------------------------|----------------------------------------------------|
| `CLEVERSWITCH_EVENT`       | `switch` \| `connect` \| `disconnect` | The event type                                     |
| `CLEVERSWITCH_DEVICE`      | `keyboard` \| `mouse`                 | The device that triggered the event                |
| `CLEVERSWITCH_DEVICE_NAME` | e.g. `MX Keys`                        | Human-readable device name                         |
| `CLEVERSWITCH_TARGET_HOST` | `1`, `2`, or `3`                      | Target host number (1-based; `switch` events only) |
| `CLEVERSWITCH_SWITCH_SOURCE` | `device` \| `edge`                  | What started the switch (`switch` events only); for `edge`, `CLEVERSWITCH_DEVICE` names a connected keyboard |

### Configuration

CleverSwitch looks for its config file at:

- **Linux / macOS:** `~/.config/cleverswitch/config.yaml`
- **Windows:** `%USERPROFILE%\.config\cleverswitch\config.yaml`

You can override this path with the `--config` CLI flag.

A starting point is provided in [`config.example.yaml`](config.example.yaml) — copy it to the path above and rename it to `config.yaml`.

Each hook is a **named** entry with the following keys:

| Key       | Description                                                                            |
|-----------|----------------------------------------------------------------------------------------|
| `path`    | A script to run directly, without a shell. Mutually exclusive with `command`.           |
| `command` | A shell command (supports pipes, `$VAR` expansion, etc). Mutually exclusive with `path`. |
| `type`    | Which event(s) fire the hook: `CONNECT`, `SWITCH`, `DISCONNECT` — a single value or a list. |
| `timeout` | Seconds before the hook process is killed (default: `5`).                               |
| `fire_for_all_devices` | Optional per-hook override of the global `hooks.fire_for_all_devices`. Set `true` to also fire for mouse events, or `false` to stay keyboard-only; omit to inherit the global default. |

Specify exactly one of `path` or `command`; setting both (or neither) logs an error and skips that hook.

```yaml
hooks:
  # Set to true to also fire hooks for mouse events (default: false)
  # fire_for_all_devices: false

  notifyOnSwitch:
    command: "notify-send 'CleverSwitch' \"Switched to host $CLEVERSWITCH_TARGET_HOST\""
    type: SWITCH

  syncDisplayInput:
    path: "~/.config/cleverswitch/on_connect.sh"
    type: [CONNECT, DISCONNECT]
    fire_for_all_devices: true   # this hook also fires for the mouse
    timeout: 10
```

## Edge Switch

Hold a modifier key (Ctrl by default) and move the cursor onto an edge of the screen to switch the keyboard and the mouse to the host you mapped to that edge — no Easy-Switch button needed. It is off until you add an `edge_switch` section to the config:

```yaml
edge_switch:
  modifier: ctrl         # ctrl | alt | shift | meta (Cmd / Win / Super), or a list: [ctrl, alt]
  cooldown_ms: 1000      # ignore repeats for this long after a switch
  edges:                 # left | right | top | bottom -> host 1..3
    left: 1
    right: 2
```

- Only the outer edges of all your monitors together count; the border between two monitors does not.
- The cursor has to move **onto** the edge while the modifier is held. Pressing the modifier while the cursor already sits at an edge does nothing, so arriving on the other host with the key still down does not bounce you back.
- The modifiers must match exactly (Ctrl+Shift does not fire a `ctrl` edge), and a held mouse button blocks it, so Ctrl-drag and Ctrl-click near an edge are safe.
- The switch is sent while the modifier is still down, so the host you leave may not see it released. If it seems stuck there, tap it once when you come back.

| Platform | Needs |
|----------|-------|
| Windows | Nothing extra. |
| macOS | Nothing extra expected. If edges never fire, grant CleverSwitch *Input Monitoring* in System Settings → Privacy & Security. |
| Linux X11 | Nothing extra. |
| Linux Wayland | Wayland does not let programs read the cursor position, so CleverSwitch reads the keyboard and mouse from `/dev/input` instead, and **pushing** the mouse `push_threshold` counts (default `800`) in one direction while the modifier is held counts as touching that edge. Reading `/dev/input` needs either membership in the `input` group (`sudo usermod -aG input $USER`, then log in again) or the opt-in udev rule [`rules.d/43-cleverswitch-input.rules`](rules.d/43-cleverswitch-input.rules), which covers Logitech devices only. Either way, programs you run can read your keystrokes from those devices, which Wayland would otherwise prevent. |

## Logs

CleverSwitch writes a size-rotated log file on every platform:

- **Linux:** `~/.local/state/cleverswitch/cleverswitch.log` (or `$XDG_STATE_HOME/cleverswitch/`). Under systemd the output also goes to the journal: `journalctl --user -u cleverswitch`.
- **macOS:** `~/Library/Logs/CleverSwitch/cleverswitch.log` (also visible in Console.app).
- **Windows:** `%LOCALAPPDATA%\CleverSwitch\Logs\cleverswitch.log`

When the file reaches its size limit it is renamed to `cleverswitch.log.1` (older ones shift to `.2`, `.3`, ...) and a fresh file is started. When run from a terminal, logs are printed there as well. If a second instance is started it logs to the console only. `-v` / `-vv` force DEBUG.

Logging is configured in the `logging:` section of the config file:

```yaml
logging:
  level: INFO          # DEBUG | INFO | WARNING | ERROR | CRITICAL
  file:
    enabled: true      # false: console only
    path: ~/cleverswitch.log
    max_size_mb: 5     # 1..1024
    backup_count: 3    # 1..50
```

When reporting a bug, please attach this log file.

## Found a Bug?

Please open a [new issue](https://github.com/MikalaiBarysevich/CleverSwitch/issues/new?template=BUG.yml).
