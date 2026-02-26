# CleverSwitch

A small, headless, cross-platform daemon that synchronizes host switching between a Logitech **MX Keys** keyboard and **MX Master 3** mouse.

When you press the Easy-Switch button on the MX Keys, CleverSwitch detects it and immediately sends the same host-switch command to the MX Master 3 — so both devices land on the same host simultaneously, with no manual button press on the mouse.

## The problem it solves

Logitech's Easy-Switch lets each device independently switch between 3 paired hosts (computers). But pressing the keyboard's host button only switches the keyboard. You have to manually press the host button on the mouse too. CleverSwitch automates this so both switch together.

## How it works

CleverSwitch communicates directly with the Logitech **Bolt USB receiver** using the **HID++ 2.0 protocol** — the same protocol Solaar uses. It does not depend on OS-level keyboard event interception.

```
User presses Easy-Switch on MX Keys
          ↓
Bolt receiver sends HID++ notification to this host
          ↓
CleverSwitch detects CHANGE_HOST notification from keyboard
          ↓
CleverSwitch sends CHANGE_HOST command to MX Master 3 via same receiver
          ↓
Both devices are now on the new host
```

The keyboard's hardware switch cannot be blocked (it is firmware-controlled), but the notification arrives at the host before the keyboard disconnects. This gives CleverSwitch a brief window (~50ms) to relay the command to the mouse.

## Requirements

- Logitech **Bolt USB receiver** (USB product ID `0xC548`) with both devices paired to it
- Python 3.10+
- `libhidapi` (see platform-specific instructions below)

## Installation

```bash
pip install cleverswitch
```

### Linux

Install udev rules to allow non-root HID access:

```bash
sudo cp udev/99-cleverswitch.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
# Unplug and replug the Bolt receiver
```

### macOS

On first run, macOS will prompt for **Input Monitoring** permission. Grant it in:
`System Preferences → Security & Privacy → Privacy → Input Monitoring`

### Windows

No special setup required. Run from a regular (non-admin) terminal.

## Configuration

Copy the example config and edit it:

```bash
cp config.example.yaml ~/.config/cleverswitch/config.yaml
```

Then run:

```bash
cleverswitch --config ~/.config/cleverswitch/config.yaml
```

See [config.example.yaml](config.example.yaml) for all options with comments.

## Hook scripts

CleverSwitch can call external scripts on events:

| Event | When |
|---|---|
| `on_switch` | A device switched host |
| `on_connect` | A device connected to the receiver |
| `on_disconnect` | A device disconnected from the receiver |

Scripts receive event details via environment variables:

```
CLEVERSWITCH_EVENT=switch
CLEVERSWITCH_DEVICE=keyboard
CLEVERSWITCH_DEVICE_NAME=MX Keys
CLEVERSWITCH_TARGET_HOST=2
CLEVERSWITCH_PREVIOUS_HOST=1
```

Scripts can be any executable (bash, Python, etc.).

## Architecture

See [docs/architecture.md](docs/architecture.md) for a full technical design.

See [docs/hidpp-protocol.md](docs/hidpp-protocol.md) for HID++ 2.0 protocol reference.

## Relation to Solaar

CleverSwitch is inspired by [Solaar](https://github.com/pwr-Solaar/Solaar) and uses the same HID++ 2.0 protocol knowledge, but is an independent, minimal implementation. It does not import or depend on Solaar.

## Platforms

| Platform | Status | HID access |
|---|---|---|
| Linux | Planned | `/dev/hidraw*` via udev |
| macOS | Planned | IOHIDManager via `hid` library |
| Windows | Planned | Windows HID API via `hid` library |
