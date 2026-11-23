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
| `CLEVERSWITCH_SWITCH_SOURCE` | `device` \| `edge`                  | What started the switch (`switch` events only); for `edge`, `CLEVERSWITCH_DEVICE` names a keyboard when one is known (a connected one first), otherwise any named device |

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

- **Host numbers are the Easy-Switch channels** marked 1, 2, 3 on the keyboard and mouse: `left: 2` switches to channel 2. To confirm which number is which, press the physical button and read `'MX Keys' switched to host N` in the log.
- Only the outer edges of all your monitors together count; the border between two monitors does not. With monitors of different heights, the shorter one's exposed side sits inside that outer box, so only the edges of the box fire.
- The cursor has to move **onto** the edge while the modifier is held. Pressing the modifier while the cursor already sits at an edge does nothing, so arriving on the other host with the key still down does not bounce you back.
- The modifiers must match exactly (Ctrl+Shift does not fire a `ctrl` edge), and a held mouse button blocks it, so Ctrl-drag and Ctrl-click near an edge are safe.
- Every device that supports CHANGE_HOST (0x1814) is switched; a device without it is left alone. With only a mouse, no SWITCH hook runs unless `hooks.fire_for_all_devices: true`, because hooks are keyboard-only by default.
- Inside a remote desktop or VM session, edge switch sees that session's cursor and fires there like anywhere else.
- The binary and source installers offer to write this section for you; the AUR package installs no config.
- Editing `edge_switch` needs a restart; the config is read once at startup.
- If edge switch cannot start (for example the permission is missing), CleverSwitch keeps running and tries again whenever a device connects.
- Run one CleverSwitch per machine. Two instances are only rejected on KDE and GNOME; anywhere else both would send their own switches.
- The switch is sent while the modifier is still down, so the host you leave may not see it released. If it seems stuck there, tap it once when you come back.

| Platform | Needs |
|----------|-------|
| Windows | Nothing extra. |
| macOS | *Input Monitoring* in System Settings → Privacy & Security, which CleverSwitch already needs. |
| Linux: X11 | Nothing extra: the X server reports the keys, buttons and cursor position. Under a systemd user service, `DISPLAY` must be in its environment (`systemctl --user import-environment DISPLAY XAUTHORITY`). |
| Linux: Hyprland | `/dev/input` read access, see [`/dev/input` access](#devinput-access). |
| Linux: KDE Plasma 6 | `/dev/input` read access, see [`/dev/input` access](#devinput-access). Nothing to install. |
| Linux: GNOME 45–51 | The CleverSwitch GNOME Shell extension, installed once. No `/dev/input` access. See [Enabling edge switch on KDE / GNOME](#enabling-edge-switch-on-kde--gnome). |
| Linux: other desktops | Not available. Other Wayland desktops (sway, niri, COSMIC...) do not tell programs where the cursor is; CleverSwitch logs a warning and keeps running without edge switch. |

### `/dev/input` access

Edge switch on Hyprland and KDE reads the keyboard and mouse through libinput, so CleverSwitch needs read access to Logitech `event*` nodes. The installer's udev rule [`rules.d/42-cleverswitch.rules`](rules.d/42-cleverswitch.rules) grants that to the logged-in user; restart CleverSwitch after installing it. Without Logitech devices, join the `input` group instead (`sudo usermod -aG input $USER`, then log in again).

The trade-off: programs you run can then read keystrokes from those Logitech devices, which Wayland otherwise prevents. This rule is how CleverSwitch already reaches HID++ over hidraw, so the capability exists either way; part 2 only widens it to `/dev/input`.

A remapper that grabs your keyboard or mouse exclusively (OpenLogi, input-remapper, keyd, kanata...) leaves the real device silent and re-sends its input through a virtual device, so CleverSwitch must be able to read that virtual device. The rule covers virtual devices that carry Logitech's vendor id, which is what OpenLogi creates; for other remappers use the `input` group.

**Turning it off.** The rule has two parts: HID++ access, which CleverSwitch always needs, and the `/dev/input` part above, which only edge switch on Hyprland and KDE uses. Comment out this line to keep only HID++ access:

```
SUBSYSTEM == "input", KERNEL == "event*", GOTO="cleverswitch_input"
```

Installed from the AUR the rule is in `/usr/lib/udev/rules.d/` and is replaced on upgrades, so edit a copy in `/etc/udev/rules.d/` (same file name), which takes precedence. Binary and source installs have it in `/etc/udev/rules.d/` already. Then reload and replug the receiver:

```
sudo udevadm control --reload-rules
sudo udevadm trigger
```

To turn it back on, delete the `/etc` copy (AUR) or undo the comment (binary/source) and reload again.

### Enabling edge switch on KDE / GNOME

Wayland keeps the cursor position away from ordinary programs, so on KDE and GNOME the desktop itself tells CleverSwitch which screen edge the cursor is on, over the session bus.

**KDE Plasma 6.** Nothing to install: while CleverSwitch runs it loads a small KWin script (`cleverswitch-edge`) and removes it when it stops. KWin scripts cannot see the keyboard, so CleverSwitch reads the held modifier from `/dev/input`, as on Hyprland — see [`/dev/input` access](#devinput-access). Plasma 5 is not supported.

**GNOME 45 to 51.** Install the CleverSwitch GNOME Shell extension once. It does nothing while CleverSwitch is not running, and GNOME then needs no `/dev/input` access.

Installed from the AUR, the extension is already in `/usr/share/gnome-shell/extensions/`, so skip to step 2. From the binary or source install, copy it:

1. Copy the extension:
   ```
   mkdir -p ~/.local/share/gnome-shell/extensions
   cp -r gnome-extension/cleverswitch@mikalaibarysevich.github.io ~/.local/share/gnome-shell/extensions/
   ```
2. Log out and back in. GNOME on Wayland only picks up new extensions at login.
3. Enable it:
   ```
   gnome-extensions enable cleverswitch@mikalaibarysevich.github.io
   ```
4. Check that `gnome-extensions info cleverswitch@mikalaibarysevich.github.io` shows the state `ACTIVE` (or `ENABLED`). If GNOME has user extensions turned off, turn them on with `gsettings set org.gnome.shell disable-user-extensions false`.

A binary or source install needs the extension copied again after upgrading CleverSwitch; the AUR package updates it. If anything is missing, CleverSwitch logs what to fix and tries again when a device connects. A modifier released and pressed again without moving the mouse is only noticed at the next mouse movement. The extension's `metadata.json` lists the GNOME versions it loads on (45 to 51 today), so a newer shell needs that list extended in a later CleverSwitch release.

### If nothing happens

`cleverswitch -v` logs the gesture at DEBUG: the modifier and button state on every change, edges ignored because they were already under the cursor when the gesture began, cooldown hits, and every switch. A healthy start names the reader, for example:

```
Edge switch reads the keys and the cursor position from GNOME Shell
Edge switch reads 5 input devices and the cursor position from Hyprland
Edge switch reads the keyboard, the buttons and the cursor position from the X server
Watching screen edges (edge-linux)
```

Anything else is one of: `Edge switch is not running: …` (with the reason, retried on the next device connection), `Edge switch cannot read any keyboard or mouse in /dev/input` (the udev rule or group, then restart), or `still unavailable` after a retry. On KDE and GNOME the message names the missing or disabled extension. To check the gesture itself without switching hosts, hold the modifier and move onto an edge while watching the log — the trace says what the detector saw.

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
