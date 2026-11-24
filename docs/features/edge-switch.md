# Edge switch

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

## `/dev/input` access

Edge switch on Hyprland and KDE reads the keyboard and mouse through libinput, so CleverSwitch needs read access to Logitech `event*` nodes. The installer's udev rule [`rules.d/42-cleverswitch.rules`](https://github.com/MikalaiBarysevich/CleverSwitch/blob/main/rules.d/42-cleverswitch.rules) grants that to the logged-in user; restart CleverSwitch after installing it. Without Logitech devices, join the `input` group instead (`sudo usermod -aG input $USER`, then log in again).

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

## Enabling edge switch on KDE / GNOME

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

## If nothing happens

Run `cleverswitch -v` in a terminal after stopping the installed instance (see [Debug output](logging.md#debug-output)). It logs the gesture at DEBUG: the modifier and button state on every change, edges ignored because they were already under the cursor when the gesture began, cooldown hits, and every switch. A healthy start names the reader, for example:

```
Edge switch reads the keys and the cursor position from GNOME Shell
Edge switch reads 5 input devices and the cursor position from Hyprland
Edge switch reads the keyboard, the buttons and the cursor position from the X server
Watching screen edges (edge-linux)
```

Anything else is one of: `Edge switch is not running: …` (with the reason, retried on the next device connection), `Edge switch cannot read any keyboard or mouse in /dev/input` (the udev rule or group, then restart), or `still unavailable` after a retry. On KDE and GNOME the message names the missing or disabled extension. To check the gesture itself without switching hosts, hold the modifier and move onto an edge while watching the log — the trace says what the detector saw.
