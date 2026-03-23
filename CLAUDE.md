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
    factory.py          # _make_logi_product: resolves CHANGE_HOST + REPROG_CONTROLS_V4 + HOSTS_INFO feature indices
    model.py            # Data classes: LogiProduct, ConnectionEvent, HostChangeEvent, ExternalUndivertEvent, DisconnectEvent
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
| HOSTS_INFO feature code | `0x1815` |
| Host-Switch CIDs | `0x00D1` → host 0, `0x00D2` → host 1, `0x00D3` → host 2 |
| HID_DEVICE_PAIRING sub_id | `0x41` (SHORT report disconnect/connect notification) |
| DISCONNECT_FLAG | `0x40` (bit 6 of byte[4] in HID_DEVICE_PAIRING SHORT report) |

## Architecture

### Dependency direction

`cli → discovery → listeners → event_processors → protocol → transport`

- `transport.py` is the **only** module that touches libhidapi (via ctypes).
- `protocol.py` knows nothing about "keyboard" or "mouse" roles.
- `listeners.py` owns message parsing but delegates event handling to `event_processors.py`.
- `factory.py` resolves feature indices, queries host pairing info for non-divertable keyboards, and builds `LogiProduct` instances.

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
2. `parse_message()` converts raw bytes into `ConnectionEvent`, `HostChangeEvent`, `ExternalUndivertEvent`, `DisconnectEvent`, or `None`.
3. Event handlers process each event:
   - `ConnectionEvent` → re-diverts Easy-Switch keys for divertable keyboards; refreshes paired host info for non-divertable keyboards.
   - `HostChangeEvent` → sends `CHANGE_HOST` to **all** products except the source device (non-divertable) or including the source (divertable, since the keypress was intercepted).
   - `ExternalUndivertEvent` → re-diverts the single affected CID.
   - `DisconnectEvent` → for non-divertable keyboards: infers the target host and sends `CHANGE_HOST` to all other products.

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

### Non-divertable keyboard host switching (disconnect-based detection)

Newer Logitech keyboards (MX Keys S, MX Keys for Business) have Easy-Switch CIDs (`0x00D1`/`0x00D2`/`0x00D3`) that are **not divertable** — `getCidInfo` returns `flags & KEY_FLAG_DIVERTABLE == 0`. These CIDs still exist on the device (same CID values as older keyboards), they simply refuse diversion. The CID values are control IDs; the corresponding task IDs are `0x00AE`/`0x00AF`/`0x00B0` (from Solaar's `special_keys.py` Task enum), but CleverSwitch works with CIDs, not tasks.

Without CID diversion, the firmware processes Easy-Switch keypresses internally and switches the RF link immediately. Over a **Bolt/Unifying receiver**, this means:

1. **No CHANGE_HOST notification arrives before the RF link drops.** The x1814 spec defines zero events — there is no spec-guaranteed notification mechanism. In practice, the keyboard switches RF channels before any notification can reach the receiver. Confirmed by logs: zero `sw_id=0` CHANGE_HOST notifications in either Windows or macOS logs.

2. **BT-direct is different.** Over Bluetooth, the connection-oriented protocol with reliable delivery (ACK'd packets) allows the notification to arrive before the BT link tears down. SwiGi (reference BT-direct implementation) catches `sw_id=0` CHANGE_HOST notifications successfully over BT. This difference is purely transport-level — the HID++ message format is identical.

3. **Other apps' responses are NOT notifications.** Logi Options+ (sw_id=`0x0D`) periodically queries `getHostInfo` (x1814 fn 0). The receiver echoes these responses to all listeners. These have the same `function_id & 0xF0 == 0x00` pattern as a genuine event 0 notification, but with a non-zero sw_id. A previous bug incorrectly matched these as host change events (filter was `sw_id != SW_ID` instead of `sw_id == 0`). Fixed by removing the broken handler entirely and using disconnect-based detection instead.

#### Detection mechanism

Instead of listening for CHANGE_HOST notifications, CleverSwitch detects the keyboard's **disconnect** from the receiver and infers the target host:

**Step 1 — Startup: query paired hosts via x1814 + x1815**

During `_make_logi_product()` in `factory.py`, for non-divertable keyboards (`divert_feat_idx is None`):

1. Resolve x1815 HOSTS_INFO feature index via ROOT GetFeature.
2. Call x1814 `getHostInfo` [fn 0] → returns `(nbHost, currHost)` where `nbHost` = total host slots (always 3 for a 3-channel device, including unpaired), `currHost` = current 0-based host index.
3. Call x1815 `getHostInfo(hostIndex)` [fn 1] for each slot 0..nbHost-1 → reply byte 1 is `status` (0=empty, 1=paired), byte 2 is `busType` (0=unused, 5=BLE Pro/Bolt).
4. Store `paired_hosts` (tuple of paired host indices, e.g., `(0, 2)`), `current_host`, and `hosts_info_feat_idx` on `LogiProduct`.

**Step 2 — Event loop: detect disconnect**

The disconnect arrives as a **SHORT HID++ 1.0 report** (report ID `0x10`, 7 bytes):
```
byte[0] = 0x10  (REPORT_SHORT)
byte[1] = slot  (device slot 1-6)
byte[2] = 0x41  (HID_DEVICE_PAIRING sub_id)
byte[3] = protocol info
byte[4] = flags | device_type  (bit 6 = DISCONNECT_FLAG = 0x40)
byte[5..6] = wireless PID
```

`parse_message()` checks for this **before** the `REPORT_LONG` filter, returning `DisconnectEvent(slot)`.

**Platform note — Windows SHORT report collection:**

On Linux/macOS, a single HID handle receives all report types (SHORT, LONG, DJ). On Windows, each report type is a separate HID collection with a different `usage`:
- `usage=0x0001` → SHORT reports (7 bytes)
- `usage=0x0002` → LONG reports (20 bytes)

CleverSwitch normally opens only the LONG collection. On Windows, `ReceiverListener` also opens the SHORT collection as `_short_transport` (via `short_hid_device_info` from discovery). The event loop polls `_short_transport` non-blocking (`read(0)`) each iteration to catch disconnect notifications. `enumerate_hid_devices` in `transport.py` accepts short-usage entries for receiver PIDs on Windows so discovery can find both collections. `_find_short_device()` in `discovery.py` matches the short-usage entry by PID.

**Step 3 — Infer target host**

`ReceiverListener._handle_disconnect()` processes `DisconnectEvent` only for non-divertable keyboards (`divert_feat_idx is None`, `role == "keyboard"`):

- **2 paired hosts** → target is deterministic: `next(h for h in paired_hosts if h != current_host)`
- **3 paired hosts** or **x1815 not supported** (paired_hosts is None) → requires `preferred_host` from config (user-facing 1-3, stored 0-indexed internally). If not configured → logs error explaining the config requirement and sets `shutdown` event to exit the app.
- Creates `HostChangeEvent(slot, target)` and delegates to `_handle_host_change()`, which sends `CHANGE_HOST` to all registry products except the source keyboard (already switched itself).

**Step 4 — Refresh on reconnect**

When the keyboard reconnects (ConnectionEvent), `_handle_connection()` calls `_refresh_paired_hosts()` for non-divertable keyboards. This re-queries x1814 + x1815 to update `paired_hosts` and `current_host`, in case the user paired a third device while on the other host.

#### Config: `preferred_host`

```yaml
settings:
  preferred_host: 2  # user-facing: 1, 2, or 3
```

Stored 0-indexed internally (`settings.preferred_host = raw_value - 1`). Required when:
- Non-divertable keyboard has 3 paired hosts (ambiguous target)
- x1815 HOSTS_INFO is not supported by the device (cannot query pairing status)

Ignored when:
- Only 2 hosts are paired (target is deterministic)
- Keyboard supports CID diversion (divertable path handles switching)

#### Key facts about CIDs on newer devices

- The Easy-Switch CIDs **are the same** (`0x00D1`/`0x00D2`/`0x00D3`) on newer keyboards like MX Keys S. The `are_es_cids_divertable()` function correctly finds them but they have `flags & KEY_FLAG_DIVERTABLE == 0`.
- The values `0x00AE`/`0x00AF`/`0x00B0` (seen in Solaar's `special_keys.py`) are **Task IDs**, not CIDs. CIDs and Tasks are separate namespaces in REPROG_CONTROLS_V4. The getCidInfo response contains both: `CID (2B) + TaskID (2B) + flags (1B)`.
- On the MX Keys S: CID `0x00D1` has task `0x00AE` (HostSwitch_Channel_1) with `flags=0x04` (not divertable).

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
- Non-divertable keyboard with 3+ paired hosts and no `preferred_host` → logs error, sets shutdown event (app exits).
- x1815 query failure during startup → graceful degradation (paired_hosts=None, treated as "needs preferred_host").
- x1815 query failure during reconnect refresh → logged at DEBUG, previous pairing data retained.

## Config location

`~/.config/cleverswitch/config.yaml` — copy from `config.example.yaml`.
