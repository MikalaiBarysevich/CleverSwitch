# CleverSwitch

A small, headless, cross-platform daemon that synchronizes host switching between Logitech keyboard and mouse.
When you press the Easy-Switch button on the keyboard, CleverSwitch detects it and immediately sends the same host-switch command to the mouse — so both devices land on the same host simultaneously.

- Runs alongside Logi Options+ or Solaar without conflicts*.
- Must be installed on every host you plan to switch from.
- Supports connections via Logitech receivers and Bluetooth.
- Tested with `MX Keys` and `MX Master 3` on Linux, macOS, and Windows.

## Support the Project

If you find this project useful, consider supporting its development:

- **Credit Card:** [Donate via Boosty](https://boosty.to/mikalaibarysevich)
- **Crypto:**
    - `BTC`: 1HXzgmGZHjLMWrQC8pgYvmcm6afD4idqr7
    - `USDT (TRC20)`: TXpJ3MHcSc144npXLuRbU81gJjD8cwAyzP

## Limitations

- **macOS + Bluetooth + Logi Options+:** When using Bluetooth-connected devices on macOS, CleverSwitch can't work correctly if Logi Options+ is running at the same time.

- **Reconnection delay:** CleverSwitch does not override device firmware. It acts as a forwarder, which means there is a small delay after reconnection. If you switch back immediately after arriving from another host, the devices may not switch together — CleverSwitch needs a moment to set everything up after reconnection.

## Installation

See [installation guide](docs/Installation.md) for full installation, update, startup, and uninstall instructions for all platforms.

#### Homebrew

Will be available once the [Homebrew formulae criteria](https://docs.brew.sh/Acceptable-Formulae#niche-or-self-submitted-stuff) are met:

> - be known (e.g. GitHub repositories should have >=30 forks, >=30 watchers or >=75 stars)
> - be used by someone other than the author


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

Each hook entry is either a plain string (a script path or shell command) or a mapping with `path` and an optional `timeout` (seconds before the hook process is killed; default: `5`).

```yaml
hooks:
  # Set to true to also fire hooks for mouse events (default: false)
  # fire_for_all_devices: false

  on_switch:
    - "notify-send 'CleverSwitch' \"Switched to host $CLEVERSWITCH_TARGET_HOST\""
    - path: "~/.config/cleverswitch/on_switch.sh"
      timeout: 10

  on_connect: []
  on_disconnect: []
```

## Found a Bug?

Please open a [new issue](https://github.com/MikalaiBarysevich/CleverSwitch/issues/new?template=BUG.yml).
