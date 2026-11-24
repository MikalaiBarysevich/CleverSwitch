# CleverSwitch

**One press — your keyboard and mouse switch to the next host together.**

CleverSwitch is a small headless daemon for Logitech keyboards and mice. It listens for the
Easy-Switch key press over HID++ and relays the same CHANGE_HOST command to every other supported
device, so your whole desk lands on the same computer at the same time.

No GUI, no companion app, no firmware changes. Runs on Linux, macOS and Windows, over receivers
and Bluetooth.

[![CI](https://github.com/MikalaiBarysevich/CleverSwitch/actions/workflows/ci.yml/badge.svg)](https://github.com/MikalaiBarysevich/CleverSwitch/actions/workflows/ci.yml)
[![Release](https://github.com/MikalaiBarysevich/CleverSwitch/actions/workflows/release.yml/badge.svg)](https://github.com/MikalaiBarysevich/CleverSwitch/releases)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE.txt)

## Features

- **Whole-desk switching** — press Easy-Switch 1, 2 or 3 on the keyboard and every connected
  device that supports CHANGE_HOST follows to the same host. No second press, no per-device setup.
- **Receivers and Bluetooth** — works through a Logitech Bolt or Unifying receiver or a direct
  Bluetooth connection. On macOS, BLE devices are read over both HID and GATT, so presses keep
  working next to Logi Options+ or OpenLogi.
- **Edge switch, optional** — hold `Ctrl` and push the cursor onto a screen edge to switch to the
  host mapped to that edge. Windows, macOS, X11, Hyprland, KDE Plasma 6 and GNOME 45–51.
  → [Set up edge switch](docs/features/edge-switch.md)
- **Hook scripts** — run your own command on switch, connect or disconnect: change the monitor
  input, send a notification, call a script. Event details arrive as `CLEVERSWITCH_*` variables,
  and hooks never block the switch itself. → [Hooks](docs/features/hooks.md)
- **Survives daily life** — hotplug and sleep/wake are handled through OS notifications instead of
  device scanning; devices are re-armed automatically after a reconnect, and discovered devices are
  cached for fast startup.
- **Quiet neighbour** — runs alongside Logi Options+ and Solaar, needs no GUI, and keeps a
  size-rotated log file on every platform.

## Quick start

| Platform | Install |
|---|---|
| Linux — Arch, Manjaro, EndeavourOS, CachyOS | [`yay -S cleverswitch`](https://aur.archlinux.org/packages/cleverswitch) |
| Linux — other distros | [pre-built binary](docs/installation.md#linux) |
| macOS | [Homebrew or pre-built binary](docs/installation.md#macos) |
| Windows | [pre-built binary](docs/installation.md#windows) |

From source? Follow the [platform-specific source instructions](docs/installation.md) — they cover
the native hidapi library, the Linux udev rules and Python setup.

1. Install CleverSwitch on **every host you want to switch from**.
2. Start it, or let the installer enable it at login.
3. Press an Easy-Switch key on the keyboard. The log confirms the relay:
   `Sending host change to 'MX Master 3' -> host 2`.

Configuration is optional — without a file, defaults are used. Copy
[`config.example.yaml`](config.example.yaml) to
`~/.config/cleverswitch/config.yaml` (`%USERPROFILE%\.config\cleverswitch\config.yaml` on Windows)
when you want hooks, edge switch or custom logging. Full reference:
[configuration](docs/configuration.md).

## How it works

```
  Easy-Switch key ──HID++──▶ CleverSwitch ──HID++ CHANGE_HOST──▶ mouse, keyboard, ...
  edge gesture ────────────▶      │
                                  └─ hook scripts (optional)
```

CleverSwitch speaks HID++ 2.0 to the devices through the receiver or the OS HID stack — the same
protocol Logi Options+ uses. It never reflashes firmware; it is a forwarder, which is why there is
a short setup delay after a device reconnects.

## Supported setups

| | |
|---|---|
| Operating systems | Linux, macOS, Windows |
| Connections | Logitech Bolt and Unifying receivers, Bluetooth |
| Devices | tested with **MX Keys** and **MX Master 3**; connected devices exposing CHANGE_HOST (`0x1814`) follow the switch |
| Requirements | macOS: Input Monitoring permission · Linux: the bundled udev rule (installed for you) · Windows: none |

## Good to know

- **Forwarder, not firmware.** After a device reconnects, CleverSwitch needs a moment to set up.
  If you switch back immediately after arriving from another host, the devices may not move
  together.
- **One instance per machine.** Two daemons would each send their own switches — only the
  edge-switch backend on KDE and GNOME refuses a second instance.
- **Edge switch has platform limits.** Other Wayland desktops (sway, niri, COSMIC…) do not expose
  the cursor position, so edge switch stays off there. See the
  [edge switch guide](docs/features/edge-switch.md).

## Documentation

| | |
|---|---|
| [Installation, update, autostart, uninstall](docs/installation.md) | all platforms |
| [Configuration](docs/configuration.md) | every key, CLI flags, cache |
| [Edge switch](docs/features/edge-switch.md) | gesture, platforms, `/dev/input`, KDE/GNOME |
| [Hooks](docs/features/hooks.md) | events, environment variables, examples |
| [Logging](docs/features/logging.md) | log locations, rotation, debug output |
| [Troubleshooting](docs/troubleshooting.md) | nothing switches, device missing, cache reset |
| [Architecture](https://github.com/MikalaiBarysevich/CleverSwitch/tree/main/docs/architecture/) | internals for contributors |

## Support the project

If CleverSwitch is useful to you, you can support its development:

- **Card:** [Boosty](https://boosty.to/mikalaibarysevich)
- **Crypto:** `BTC` `1HXzgmGZHjLMWrQC8pgYvmcm6afD4idqr7` ·
  `USDT (TRC20)` `TXpJ3MHcSc144npXLuRbU81gJjD8cwAyzP`

## License

[GPL-3.0-or-later](LICENSE.txt)

Found a bug? [Open an issue](https://github.com/MikalaiBarysevich/CleverSwitch/issues/new?template=BUG.yml)
and attach the log file described in [Logging](docs/features/logging.md) — it makes a fix much faster.
