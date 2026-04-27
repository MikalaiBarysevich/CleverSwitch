# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Headless Python daemon that synchronizes Logitech Easy-Switch host switching between a keyboard and mouse. When the keyboard's Easy-Switch button is pressed, CleverSwitch detects the HID++ notification and immediately sends the same CHANGE_HOST command to the mouse — so both switch together.

Communication is via **HID++ 2.0** directly over the Logitech **Bolt USB receiver** (or Unifying receiver / Bluetooth).

## Project specific rules
- For any hid command related work/question ask dedicated @hidpp-protocol-expert agent
- Delegate all design work to the @software-architect agent
- If a code change implies touching more than 5 files delegate it to the @senior-fullstack-engineer agent
- Never assume. If you don't know what to do - you must ask.
- You must design with existing event-driven architecture in mind first.

## Tech stack

- **Python 3.14+**
- `hid` — cross-platform HID access
- `pyyaml` — config file parsing
- `pytest` + `pytest-mock` + `pytest-cov` — testing
- `ruff` — linting and formatting (line-length 120)
- All log calls must use f-strings: `log.info(f"wpid=0x{wpid:04X}")` — never `%s`/`%d` style. `wpid` and `pid` values must always be formatted as `0x{value:04X}`.

## Development commands

```bash
# Full pre-commit check (tests + format + lint) — run before committing
./.git/hooks/pre-commit

# Fast feedback during development (no coverage enforcement, stop on first failure)
pytest --no-cov -x

# Run a single test by name
pytest -k test_reconnection_publishes_set_report_flag_event_when_reprog_available

# Run a single test file
pytest tests/cleverswitch/subscriber/test_device_connected_subscriber.py

# After editing any scripts/mac/*.command file, restore the executable bit —
# the Edit tool resets it on disk and git will record the mode change as a regression:
git update-index --chmod=+x scripts/mac/<file>.command
```

## Architecture

### Pub-sub event system

The core of the architecture is a typed pub-sub system with one daemon thread per subscriber.

**`Topics`** (`topic/topics.py`) is a typed dataclass with five channels:
- `hid_event` — all inbound HID++ events (DeviceConnectedEvent, HidppResponseEvent, HidppNotificationEvent, HidppErrorEvent, etc.)
- `write` — outbound HID messages (WriteEvent)
- `device_info` — triggers device setup (DeviceInfoRequestEvent)
- `flags` — apply/re-apply key reporting flags (SetReportFlagEvent); `SetReportFlagSubscriber` selects analytics mode (byte 9) or divert mode (byte 6) based on `device.supported_flags`
- `info_progress` — task completion feedback (InfoTaskProgressEvent)

**`Topic`** (`topic/topic.py`) — each `subscribe(subscriber)` call creates a private `queue.Queue` and a daemon thread that drains it by calling `subscriber.notify(event)`. `publish(event)` enqueues on all subscriber queues simultaneously.

**Subscribers** implement `notify(event) -> None` and filter by event type internally. All subscribers call `topics.<channel>.subscribe(self)` in `__init__`.

### Device lifecycle

```
discovery.py
  └── HidGateway (thread, one per HID collection)
      └── EventListener (thread, reads raw bytes → parses → publishes to hid_event)
      └── ConnectionTrigger.trigger() → enables HID++ notifications, then sends enumeration message
           → DeviceConnectedEvent published to hid_event

DeviceConnectionSubscriber.notify(DeviceConnectedEvent)
  ├── new device + link_established=True  → LogiDevice registered, DeviceInfoRequestEvent published
  ├── new device + link_established=False → skipped (stale pairing entry from receiver enumeration)
  └── reconnect → logi_device.connected updated, SetReportFlagEvent re-published if supported_flags known

DeviceInfoSubscriber.notify(DeviceInfoRequestEvent)
  └── starts InfoTask threads: CidReportingFeatureTask, ChangeHostFeatureTask, NameAndTypeFeatureTask

InfoTask (Thread + Subscriber)
  ├── doTask() — sends HID++ requests via write topic, blocks on response queue
  ├── on success: removes step from device.pending_steps, fires dependent tasks
  └── publishes InfoTaskProgressEvent to info_progress

InfoTaskOrchestrator.notify(InfoTaskProgressEvent)
  ├── success + pending_steps empty → logs "Device fully discovered" (once per wpid)
  └── failure + device.connected → retries the task immediately
```

### InfoTask design

`InfoTask` (`subscriber/task/info_task.py`) is abstract, `Thread`, and `Subscriber`:
- Subscribes to `hid_event`; `notify()` filters on `slot + pid + sw_id` and enqueues matching `HidppResponseEvent` / `HidppErrorEvent`
- `_send_request(*params)` builds a long-format HID++ message and publishes a `WriteEvent`
- `_wait_response(timeout=2.0)` blocks on the private queue; returns `None` on timeout
- `run()` checks `step_name in device.pending_steps`; skips `doTask()` if already complete; always publishes `InfoTaskProgressEvent`

Task dependency chain:
- `CidReportingFeatureTask` → fires `FindESCidsFlagsTask`
- `NameAndTypeFeatureTask` → fires `GetDeviceTypeTask` + `GetDeviceNameTask`
- `ChangeHostFeatureTask` has no dependents

Each task type has a unique `sw_id` constant in `subscriber/task/constants.py` (values 8–13). SW_IDs must stay distinct from each other and from `SW_ID = 0x08` in `hidpp/constants.py` (same value as `FEATURE_REPROG_CONTROLS_V4_SW_ID`).

### Receiver enable-notifications message

`ReceiverConnectionTrigger` sends `ENABLE_HIDPP_NOTIFICATIONS_MESSAGE` (SET_REGISTER 0x00 with `r1=0x09`: wireless notifications + software present) before the enumeration message. The receiver's register 0x00 is RAM-only and defaults to 0 at USB power-up, which blocks 0x41 device-connection notifications. Without enabling first, fresh-plugged receivers (notably on macOS) deliver no connection events.

### LogiDevice state

`model/logi_device.py` — mutable dataclass tracking:
- `available_features: dict[int, int]` — feature code → feature index (populated by feature tasks)
- `pending_steps: set[str]` — setup steps not yet completed
- `supported_flags: set[int]` — ES key capability flags (KEY_FLAG_DIVERTABLE, KEY_FLAG_PERSISTENTLY_DIVERTABLE, KEY_FLAG_ANALYTICS); populated by `FindESCidsFlagsTask`; all ES CIDs share the same flags so this is per-device, not per-CID
- `connected: bool` — current connection state (gates orchestrator retries)
- `role`, `name` — populated during setup

### Wiring

`setup/app_setup.py:setup_context()` creates Topics, LogiDeviceRegistry, and all subscribers. It is the single place where components are connected.

Active subscribers: `DeviceConnectionSubscriber`, `DeviceInfoSubscriber`, `InfoTaskOrchestrator`, `SetReportFlagSubscriber`, `ExternalUnsetFlagSubscriber`, `HostChangeSubscriber`, `EventHookSubscriber`, `WirelessStatusSubscriber`.

The parser detects ES CID presses (fn=0 diverted, fn=2 analytics press-only) and emits `HostChangeEvent` instead of generic `HidppNotificationEvent`. `HostChangeSubscriber` reacts to `HostChangeEvent` and sends CHANGE_HOST to all registered devices.

`EventHookSubscriber` listens on `hid_event` for `HostChangeEvent` and `DeviceConnectedEvent`, and fires user-configured hook scripts/commands asynchronously via `hooks.py`. Hooks support both file paths (run without shell) and inline shell commands (auto-detected by prefix heuristic: `/`, `~/`, `./`, `../` → file path, otherwise shell command). By default hooks only fire for keyboard events; set `hooks.fire_for_all_devices: true` in config to include mouse events.

`ExternalUnsetFlagSubscriber` detects when an external app (Solaar, logiops) clears the ES key reporting flag via `setCidReporting` (fn=3, sw_id in 1–7). The parser emits `ExternalUnsetFlagEvent`; the subscriber re-publishes `SetReportFlagEvent` to restore the flag.

## Testing conventions

- All HID I/O is mocked — tests never open real devices.
- `conftest.py` in the root `tests/` directory provides `FakeTransport`, `fake_transport`, and `make_fake_transport` fixtures.
- Subscriber tests construct `Topics` with `MagicMock(spec=Topic)` for all channels and assert `publish.assert_called_once()` / `assert_not_called()`. See skill: `@write-subscriber-test`.
- `transport.py` and `__main__.py` are excluded from coverage (hardware I/O and entry point).
- Coverage threshold: **90%** (enforced in `pyproject.toml`).
