# CleverSwitch — Claude Code Guide

## Project overview

Headless Python daemon that synchronizes Logitech Easy-Switch host switching between a keyboard and mouse.
When the keyboard's Easy-Switch button is pressed, CleverSwitch detects the HID++ notification and immediately sends the same CHANGE_HOST command to the mouse — so both switch together.

Communication is via **HID++ 2.0** directly over the Logitech **Bolt USB receiver** (or Unifying receiver).
No dependency on Solaar, no OS-level key interception.

## Tech stack

- **Python 3.10+** (currently running 3.14 in venv)
- `libhidapi` — cross-platform HID access (loaded via ctypes, no Python `hid` package)
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
    discovery.py        # Background discovery loop: enumerates HID devices, creates PathListeners
    listeners.py        # PathListener thread: per-receiver event loop, device probing, message parsing
    event_processors.py # ConnectionProcessor, HostChangeProcessor, ExternalUndivertProcessor
    factory.py          # _make_logi_product: resolves CHANGE_HOST + REPROG_CONTROLS_V4 feature indices
    model.py            # Data classes: LogiProduct, ConnectionEvent, HostChangeEvent, ExternalUndivertEvent, EventProcessorArguments
    hooks.py            # External script execution (ThreadPoolExecutor)
    hidpp/
        transport.py    # Low-level HID open/read/write via ctypes binding to libhidapi
        protocol.py     # HID++ 2.0 message construction, request/reply, feature operations
        constants.py    # Feature codes, report IDs, product IDs, CID mappings

rules.d/42-cleverswitch.rules  # Linux udev rule for hidraw access
config.example.yaml          # Annotated reference config
tests/                       # Unit tests (mocked HID transport)
```

## Key constants

| Thing | Value |
|---|---|
| Logitech vendor ID | `0x046D` |
| Bolt receiver PID | `0xC548` |
| Unifying receiver PIDs | `0xC52B`, `0xC532` |
| CHANGE_HOST feature code | `0x1814` |
| REPROG_CONTROLS_V4 feature | `0x1B04` |
| DEVICE_TYPE_AND_NAME feature | `0x0005` |
| Host-Switch CIDs | `0x00D1` → host 0, `0x00D2` → host 1, `0x00D3` → host 2 |

## Architecture

### Dependency direction

`cli → discovery → listeners → event_processors → protocol → transport`

- `transport.py` is the **only** module that touches libhidapi (via ctypes).
- `protocol.py` knows nothing about "keyboard" or "mouse" roles.
- `listeners.py` owns message parsing but delegates event handling to `event_processors.py`.
- `factory.py` resolves feature indices and builds `LogiProduct` instances.

### Threading model

```
cli.py:main()
└── discover(shutdown)              # background discovery loop
    └── PathListener(device, shutdown)  # one thread per receiver path
        ├── detect_products()       # probe slots 1-6 on startup
        └── run()                   # event loop: read → parse → process
```

- `discovery.py` enumerates HID devices, creates one `PathListener` per receiver.
- Each `PathListener` runs in its own thread, owns one `HIDTransport`, and maintains a `dict[int, LogiProduct]` for its slots.
- Event processors are stateless — they receive `EventProcessorArguments` and act on them.

### Message flow

1. `PathListener.run()` reads raw HID++ packets from the transport.
2. `parse_message()` converts raw bytes into `ConnectionEvent`, `HostChangeEvent`, `ExternalUndivertEvent`, or `None`.
3. Event processors handle each event:
   - `ConnectionProcessor`: on `ConnectionEvent`, re-diverts Easy-Switch keys (CIDs D1/D2/D3) for the keyboard.
   - `HostChangeProcessor`: on `HostChangeEvent`, sends `CHANGE_HOST` to **all** products on this receiver.
   - `ExternalUndivertProcessor`: on `ExternalUndivertEvent`, re-diverts the single affected CID.

### Protocol layer

- **All messages are long format** (report 0x11, 20 bytes). HID++ 2.0 responses are always long, and on Windows each report type is a separate HID collection.
- `request()` sends a long message and waits for a matching reply (by SW_ID and request_id).
- `request_write_only()` sends without waiting for a reply (used for `setCidReporting`).
- `send_change_host()` is fire-and-forget — no reply expected after host switch.

### Connection events

Two sources of reconnection events are handled:
- **DJ pairing** (report 0x20, feature 0x42, address 0x00) — Unifying/Bolt receiver slot connect.
- **x1D4B Wireless Device Status** (report 0x11, feature_id 0x04, byte[4]=0x01) — always-enabled reconnection notification.

On reconnection, `ConnectionProcessor` re-diverts the Easy-Switch keys so host-switch detection continues working.

### External undivert detection

When another application (e.g. Solaar) sends a `setCidReporting` (fn 0x30 of REPROG_CONTROLS_V4) that undiverts an Easy-Switch CID, the device echoes the response to all listeners. `parse_message()` detects these by checking:
- `feature_id` matches the product's `divert_feat_idx`
- Upper nibble of byte[3] is `0x30` (setCidReporting function)
- Lower nibble of byte[3] (sw_id) is not `0` (notification) and not `SW_ID` (our own)
- The CID in byte[5] is a known HOST_SWITCH_CID

This produces an `ExternalUndivertEvent`, and `ExternalUndivertProcessor` re-diverts just that single CID.

### Discovery and re-plug recovery

`discover()` runs a background loop that enumerates HID devices every 0.5s. It maintains a `dict[bytes, PathListener]` keyed by device path:
- **New path**: creates and starts a new `PathListener` thread.
- **Disappeared path**: calls `stop()` on the listener and removes it from the dict.
- **Re-plug**: when a receiver is unplugged, the `PathListener` dies on `TransportError`. Discovery detects the path disappearance, removes the dead listener, and on next enumeration creates a fresh one for the re-plugged device.

## Workflow

After updating tests, always verify with `./.git/hooks/pre-push` before committing.

## Testing conventions

- All HID I/O is mocked — tests never open real devices.
- `conftest.py` provides `FakeTransport`, `fake_transport`, and `make_fake_transport` fixtures.
- `transport.py` and `__main__.py` are excluded from coverage (hardware I/O and entry point).
- Coverage threshold: **90%** (enforced in `pyproject.toml`).

## Error handling

- `TransportError` → logged, transport closed, listener exits.
- `ConfigError` → fatal at startup with clear message.
- Hook failures → log WARNING only, never block event loop.
- Read timeout → not an error, normal poll heartbeat.
- `set_cid_divert` failure → logged as warning, does not crash.
- `send_change_host` failure → raises `TransportError`.

## Config location

`~/.config/cleverswitch/config.yaml` — copy from `config.example.yaml`.
