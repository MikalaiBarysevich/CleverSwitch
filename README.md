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
| `switch`     | The Easy-Switch button was pressed and a host change was sent |
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

## Found a Bug?

Please open a [new issue](https://github.com/MikalaiBarysevich/CleverSwitch/issues/new?template=BUG.yml).
