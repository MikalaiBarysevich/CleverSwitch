# CleverSwitch

A small, headless, cross-platform daemon that synchronizes host switching between a Logitech keyboard and mouse which both support multiple hosts.
When you press the Easy-Switch button on a logi keyboard, CleverSwitch detects it and immediately sends the same host-switch command to a logi mouse - so both devices land on the same host simultaneously.

## Installation

```bash
pip install cleverswitch
```

### Linux

Install udev rules to allow non-root HID access:

```bash
sudo cp udev/99-cleverswitch.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
# Unplug and replug the receiver
```

#### Run on Startup
TBD

### macOS

On first run, macOS will prompt for **Input Monitoring** permission. Grant it in:
`System Preferences → Security & Privacy → Privacy → Input Monitoring`

#### Run on Startup
TBD

### Windows

No special setup required. Run from a regular (non-admin) terminal.
If no device found check driver in driver manager. Need to be default hid windows driver

## Configuration

TBD

## Hook scripts

CleverSwitch can call external scripts on events: 

| Event           | When                                    |
|-----------------|-----------------------------------------|
| `on_switch`     | A device switched host                  |

Scripts receive event details via environment variables:

```
CLEVERSWITCH_EVENT=switch
CLEVERSWITCH_DEVICE=keyboard
CLEVERSWITCH_DEVICE_NAME=MX Keys
CLEVERSWITCH_TARGET_HOST=2
```

Scripts can be any executable (bash, Python, etc.).

## Relation to Solaar

CleverSwitch is inspired by [Solaar](https://github.com/pwr-Solaar/Solaar) and uses the same HID++ 2.0 protocol knowledge, but is an independent, minimal implementation. It does not import or depend on Solaar.
