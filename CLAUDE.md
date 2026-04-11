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
      └── ConnectionTrigger.trigger() → sends enumeration message / 0xB5 queries
           → DeviceConnectedEvent published to hid_event

DeviceConnectionSubscriber.notify(DeviceConnectedEvent)
  ├── new device  → LogiDevice registered, DeviceInfoRequestEvent published to device_info
  └── reconnect  → logi_device.connected updated, SetReportFlagEvent re-published if supported_flags known

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

Each task type has a unique `sw_id` constant in `subscriber/task/constants.py` (values 8–13). SW_IDs must stay distinct from each other and from the ping SW_ID (`SW_ID = 0x08` in `hidpp/constants.py` — same value as `FEATURE_REPROG_CONTROLS_V4_SW_ID`; disambiguated by `feature_index == 0` check in `DisconnectPollerSubscriber`).

### Platform differences (macOS)

On macOS the receiver does not send spontaneous device connection events, so two macOS-only subscribers are activated:
- **`WirelessReconnectSubscriber`** — detects x1D4B (Wireless Device Status) notifications; on reconnect fires `DeviceConnectedEvent(link_established=True)` so reconnect flow triggers
- **`DisconnectPollerSubscriber`** — pings all registered devices every 0.5s; fires `DeviceConnectedEvent(link_established=False)` on timeout

**`ReceiverConnectionTriggerMac`** (`connection/trigger/receiver_trigger_mac.py`) — at startup queries the 0xB5 pairing register for each slot (static NVM data, all ever-paired devices). The parser returns `link_established=False` for these to avoid starting setup for sleeping devices. Setup only starts when a live connection is confirmed (x1D4B or ping response).

### LogiDevice state

`model/logi_device.py` — mutable dataclass tracking:
- `available_features: dict[int, int]` — feature code → feature index (populated by feature tasks)
- `pending_steps: set[str]` — setup steps not yet completed
- `supported_flags: set[int]` — ES key capability flags (KEY_FLAG_DIVERTABLE, KEY_FLAG_PERSISTENTLY_DIVERTABLE, KEY_FLAG_ANALYTICS); populated by `FindESCidsFlagsTask`; all ES CIDs share the same flags so this is per-device, not per-CID
- `connected: bool` — current connection state (gates orchestrator retries)
- `role`, `name` — populated during setup

### Wiring

`setup/app_setup.py:setup_context()` creates Topics, LogiDeviceRegistry, and all subscribers. It is the single place where components are connected. Platform-specific subscribers (`DisconnectPollerSubscriber`, `WirelessReconnectSubscriber`) are guarded with `if get_system() == "Darwin"`.

Active subscribers: `DeviceConnectionSubscriber`, `DeviceInfoSubscriber`, `InfoTaskOrchestrator`, `SetReportFlagSubscriber`, `ExternalUnsetFlagSubscriber`, `HostChangeSubscriber`, `WirelessStatusSubscriber` (+ macOS-only: `DisconnectPollerSubscriber`, `WirelessReconnectSubscriber`).

`HostChangeSubscriber` handles two notification paths on the `hid_event` channel: fn=0 (diverted key press, `HidppNotificationEvent`) and fn=2 (analytics key press, payload[2]=0x01 for press only). Both send CHANGE_HOST to all registered devices.

`ExternalUnsetFlagSubscriber` detects when an external app (Solaar, logiops) clears the ES key reporting flag via `setCidReporting` (fn=3, sw_id in 1–7). The parser emits `ExternalUnsetFlagEvent`; the subscriber re-publishes `SetReportFlagEvent` to restore the flag.

## Testing conventions

- All HID I/O is mocked — tests never open real devices.
- `conftest.py` in the root `tests/` directory provides `FakeTransport`, `fake_transport`, and `make_fake_transport` fixtures.
- Subscriber tests construct `Topics` with `MagicMock(spec=Topic)` for all channels and assert `publish.assert_called_once()` / `assert_not_called()`. See skill: `@write-subscriber-test`.
- `transport.py` and `__main__.py` are excluded from coverage (hardware I/O and entry point).
- Coverage threshold: **90%** (enforced in `pyproject.toml`).
