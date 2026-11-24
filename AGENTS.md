# CleverSwitch — agent instructions

Headless Python daemon that synchronizes Logitech Easy-Switch host switching between a keyboard and mouse. When the keyboard's Easy-Switch button is pressed, CleverSwitch detects the HID++ notification and immediately sends the same CHANGE_HOST command to the mouse — so both switch together.

Communication is via **HID++ 2.0** directly over the Logitech **Bolt USB receiver** (or Unifying receiver / Bluetooth). The project runs on Linux, macOS and Windows.

## Working rules

- **Never assume.** If a requirement, config value or platform behaviour is unclear, ask before changing code.
- Design with the existing event-driven architecture in mind first: events over topics, one daemon thread per subscriber, no new polling loops.
- Design work starts with a short design note (PR description, or a new file under `docs/architecture/` if it outlives the change), not with code.
- **HID++ protocol questions** (feature codes, message layouts, error codes, registers, report formats): load the `hidpp-protocol` skill and read the referenced documentation. Never guess protocol details.
- Read only the architecture doc for the subsystem you touch — see *Where to look*. Do not load all of `docs/architecture/` by default.
- Log calls use f-strings only: `log.info(f"wpid=0x{wpid:04X}")` — never `%s`/`%d` style. `wpid` and `pid` values are always formatted as `0x{value:04X}`.
- Label devices in logs and hooks with `device.display_name`, never `device.name`.
- When behaviour changes, update the matching doc under `docs/architecture/` (skill: `update-agents-md`). Stale docs are worse than missing ones.
- After any file edit, verify the executable bit survived on `scripts/mac/*.command` and `scripts/*.sh`; file-rewriting tools drop it and git records the mode change as a regression. Restore with `git update-index --chmod=+x <path>`.

## Tech stack

- **Python 3.14+**
- `hid` — cross-platform HID access
- `pyyaml` — config file parsing
- `bleak` + `pyobjc-framework-CoreBluetooth` — macOS-only, used by `GattChannel` for the BLE notify path
- `jeepney` — Linux-only, the session bus that KWin and GNOME Shell report screen edges over
- `pytest` + `pytest-mock` + `pytest-cov` — testing
- `ruff` — linting and formatting (line-length 120)

## Development commands

```bash
# Full suite with the coverage gate — run before committing
pytest

# Fast feedback during development (no coverage enforcement, stop on first failure)
pytest --no-cov -x

# Lint and format
ruff format --check
ruff check

# Run a single test by name
pytest -k test_reconnection_publishes_set_report_flag_event_when_reprog_available

# Run a single test file
pytest tests/cleverswitch/subscriber/test_device_connected_subscriber.py

# Restore an executable bit after a file edit
git update-index --chmod=+x scripts/mac/<file>.command
```

## Where to look

| Subsystem | Doc |
|---|---|
| Topics, subscribers, threading model | `docs/architecture/pub-sub.md` |
| Discovery → hotplug → DeviceLink → channels, receiver arming | `docs/architecture/device-lifecycle.md` |
| InfoTask, discovery retries, step dependencies, sw_id allocation | `docs/architecture/info-tasks.md` |
| macOS BLE/GATT hybrid transport | `docs/architecture/macos-ble.md` |
| Edge switch backends, detector, hooks | `docs/architecture/edge-switch.md` |
| Logging, config, instance lock | `docs/architecture/logging.md` |
| LogiDevice state, device cache | `docs/architecture/device-model.md` |
| Subscriber wiring in `app_setup` | `docs/architecture/wiring.md` |
| Historic hotplug design | `docs/hotplug-design.md` |

## Testing conventions

- All HID I/O is mocked — tests never open real devices.
- `conftest.py` in the root `tests/` directory provides `FakeTransport`, `fake_transport`, and `make_fake_transport` fixtures.
- Subscriber tests construct `Topics` with `MagicMock(spec=Topic)` for all channels and assert `publish.assert_called_once()` / `assert_not_called()`. Pattern: `write-subscriber-test` skill.
- `InfoTask` tests must feed responses with `tests/task_helpers.py:deliver_on_request(task, topics, [...])`, which delivers one response per published request. Pre-loading `task._response_queue` does not work — `_send_request` drains it, because that ordering cannot happen on real hardware.
- `transport.py`, `__main__.py`, `hotplug/linux/netlink_backend.py`, `hotplug/macos/iokit.py`, `hotplug/windows/cfgmgr32.py` and the edge-switch bindings `edgeswitch/windows/user32.py`, `edgeswitch/macos/quartz.py`, `edgeswitch/linux/xcb.py`, `edgeswitch/linux/libinput.py`, `edgeswitch/linux/session_bus.py` are excluded from coverage (hardware I/O, entry point, OS glue). Keep parsing and threading out of the OS glue (e.g. `hotplug/linux/udev_message.py`, `hotplug/windows/interface_name.py`; the IOKit and CfgMgr backends take an injectable factory) so it stays tested.
- Coverage threshold: **90%** (enforced in `pyproject.toml`).
