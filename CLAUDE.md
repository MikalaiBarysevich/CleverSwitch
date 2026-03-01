# CleverSwitch — Claude Code Guide

## Project overview

Headless Python daemon that synchronizes Logitech Easy-Switch host switching between a keyboard and mouse.
When the keyboard's Easy-Switch button is pressed, CleverSwitch detects the HID++ notification and immediately sends the same CHANGE_HOST command to the mouse — so both switch together.

Communication is via **HID++ 2.0** directly over the Logitech **Bolt USB receiver** (or Bluetooth).
No dependency on Solaar, no OS-level key interception.

## Tech stack

- **Python 3.10+** (currently running 3.14 in venv)
- `hid` — cross-platform HID access (wraps libhidapi)
- `pyyaml` — config file parsing
- `pytest` + `pytest-mock` + `pytest-cov` — testing
- `ruff` — linting and formatting (line-length 120)

## Development commands

```bash
# Run all tests (requires ≥90% coverage — enforced by pyproject.toml)
pytest

# Lint
ruff check src

# Format
ruff format src

# Install in editable mode
pip install -e ".[dev]"
```

Pre-push hook runs automatically: `pytest` → `ruff format src` → `ruff check src`.

## Directory structure

```
src/cleverswitch/
    cli.py              # Argument parsing, config loading, daemon startup
    config.py           # YAML config schema and dataclasses
    errors.py           # Exception hierarchy
    platform_setup.py   # Platform-specific prerequisite checks (udev, permissions)
    discovery.py        # Device discovery: Bolt receiver slots + Bluetooth scan
    monitor.py          # Main event loop: read notifications, dispatch events
    hooks.py            # External script execution (ThreadPoolExecutor)
    hidpp/
        transport.py    # Low-level HID open/read/write — only file that imports `hid`
        protocol.py     # HID++ 2.0 message construction and parsing
        constants.py    # Feature codes, report IDs, product IDs

udev/99-cleverswitch.rules   # Linux udev rule for hidraw access
config.example.yaml          # Annotated reference config
tests/                       # Unit tests (mocked HID transport)
```

## Key constants

| Thing | Value |
|---|---|
| Logitech vendor ID | `0x046D` |
| Bolt receiver product ID | `0xC548` |
| CHANGE_HOST feature code | `0x1814` |
| REPROG_CONTROLS_V4 feature | `0x1B04` |
| Bluetooth devnumber | `0xFF` (DEVICE_RECEIVER) |

## Architecture rules

- Dependency direction is strictly top-down: `cli → monitor → discovery → protocol → transport`.
- `transport.py` is the **only** module that imports `hid`.
- `protocol.py` knows nothing about "keyboard" or "mouse" roles.
- `monitor` know nothing about raw bytes.
- No shared mutable state between threads. Hook runner gets a plain dict snapshot.

## Discovery flow

`discover(cfg)` in `discovery.py`:
1. Scan Bolt/Unifying receivers — reads pairing register wpid for each slot 1–6.
2. If both devices not found, scan Bluetooth by btid.
3. For each found device, resolve CHANGE_HOST feature index (and REPROG_CONTROLS_V4 for keyboard).
4. Returns `Setup(devices: list[DeviceContext])`.

Bluetooth devices use `devnumber=0xFF` and `long_msg=True`.

## Testing conventions

- All HID I/O is mocked — tests never open real devices.
- `conftest.py` provides shared fixtures for mock transports.
- `transport.py` and `__main__.py` are excluded from coverage (hardware I/O and entry point).
- Coverage threshold: **90%** (enforced in `pyproject.toml`).

## Error handling

- `ReceiverNotFound` / `TransportError` → retry loop with `retry_interval_s`.
- `FeatureNotSupported` / `ConfigError` → fatal at startup with clear message.
- Hook failures → log WARNING only, never block monitor loop.
- Read timeout → not an error, normal poll heartbeat.

## Config location

`~/.config/cleverswitch/config.yaml` — copy from `config.example.yaml`.
