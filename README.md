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

## Two-Host Fallback (`peer_host_index`)

CleverSwitch's normal relay listens for the keyboard's own "I just switched host" announcement and forwards it to the mouse. **On some device/receiver combinations - notably MX Keys S paired through a Logitech Bolt receiver - that announcement never arrives at all.** Confirmed via raw HID capture on both Linux and macOS: the departing host receives nothing but a bare disconnect, no target-host information whatsoever, on every Easy-Switch press. Without that information there's nothing for the normal relay to forward, and the mouse (or keyboard, if the mouse switched first) never follows - no amount of listening differently or waiting longer fixes this, because the departing host is the only place such an announcement could ever arrive in the first place.

`easy_switch.peer_host_index` is an **opt-in fallback for the common two-machine setup**. Instead of waiting for a switch announcement, it reacts to a plain disconnect: whenever either device disconnects here while its paired counterpart is still connected here, the counterpart is commanded to follow to a fixed, pre-configured host number. Unlike Logitech's own keyboard-only Enhanced Easy-Switch, this is symmetric - pressing the mouse's Easy-Switch key also brings the keyboard along.

This is an **alternative path, not a replacement** for the normal relay: both mechanisms are always active. If your device does emit the switch announcement, that still fires first and this fallback never triggers. Only configure this if the normal relay doesn't work for you.

**Trade-off:** there is no way to tell an intentional Easy-Switch press apart from an ordinary RF dropout on the wire, so a device that merely goes out of range or loses power will also (incorrectly) send its counterpart away. Only enable this if you have exactly two machines and are comfortable with that trade-off.

Configuration is keyed **by device role**, not a single shared number - each device keeps its own independent host pairing table, so the keyboard's and the mouse's index for "the same other machine" aren't guaranteed to match:

```yaml
easy_switch:
  peer_host_index:
    keyboard: 2
    mouse: 2
```

To find each value: on the target machine, with that device connected there, run `cleverswitch -vv` and look for a `getHostInfo`-style response (or ask in the project's issue tracker for a small helper script). Host numbers are 1-based, like `CLEVERSWITCH_TARGET_HOST` above.

## Found a Bug?

Please open a [new issue](https://github.com/MikalaiBarysevich/CleverSwitch/issues/new?template=BUG.yml).
