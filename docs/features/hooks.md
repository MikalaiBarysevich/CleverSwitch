# Hook scripts

Hook scripts let you run custom commands or scripts in response to CleverSwitch events. Hooks are executed asynchronously and never block the switch relay.
Use this when you need extra logic, for example switching the display input source when a device connects to the current PC.

By default, hooks only fire for keyboard events. Set `hooks.fire_for_all_devices: true` in config to include mouse events as well.

The config file lives at `~/.config/cleverswitch/config.yaml` (`%USERPROFILE%\.config\cleverswitch\config.yaml` on Windows) unless `--config` is passed. See [Configuration](../configuration.md) for the full file reference.

## Events

| Event        | When it fires                                                 |
|--------------|---------------------------------------------------------------|
| `switch`     | The Easy-Switch button was pressed, or an edge switch fired, and a host change was sent |
| `connect`    | A device connected (including wake from sleep)                |
| `disconnect` | A device disconnected (including sleep)                       |

## Environment variables

Each hook receives the following environment variables:

| Variable                   | Values                                | Description                                        |
|----------------------------|---------------------------------------|----------------------------------------------------|
| `CLEVERSWITCH_EVENT`       | `switch` \| `connect` \| `disconnect` | The event type                                     |
| `CLEVERSWITCH_DEVICE`      | `keyboard` \| `mouse`                 | The device that triggered the event                |
| `CLEVERSWITCH_DEVICE_NAME` | e.g. `MX Keys`                        | Human-readable device name                         |
| `CLEVERSWITCH_TARGET_HOST` | `1`, `2`, or `3`                      | Target host number (1-based; `switch` events only) |
| `CLEVERSWITCH_SWITCH_SOURCE` | `device` \| `edge`                  | What started the switch (`switch` events only); for `edge`, `CLEVERSWITCH_DEVICE` names a keyboard when one is known (a connected one first), otherwise any named device |

## Configuration

A starting point is provided in [`config.example.yaml`](../../config.example.yaml) — copy it to the config path above and rename it to `config.yaml`.

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
