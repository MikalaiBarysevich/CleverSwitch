# CleverSwitch

A small, headless, cross-platform daemon that synchronizes host switching between Logitech keyboard and mouse.
When you press the Easy-Switch button on the keyboard, CleverSwitch detects it and immediately sends the same host-switch command to the mouse — so both devices land on the same host simultaneously.

- Runs alongside Logi Options+ or Solaar without conflicts.
- Must be installed on every host you plan to switch from.
- Currently supports connections via Logitech receivers only. You can switch _to_ a Bluetooth host, but not switch _back_ from Bluetooth.
- Tested with `MX Keys` and `MX Master 3` on Linux, macOS, and Windows.

> CleverSwitch does not override device firmware. It acts as a forwarder, which means there is a small delay
> after reconnection. If you switch back immediately after arriving from another host, the devices may not
> switch together — CleverSwitch needs a moment to set everything up after reconnection.

## Installation

### From Sources (the only Linux and macOS option for now)

_Requires Python >=3.10 on PATH._

1. Clone the repository.
2. Install from root:
```bash
pip install .
```
3. Run:
```bash
cleverswitch
```

#### Windows

The [hidapi DLL](https://github.com/libusb/hidapi/releases) must be downloaded manually and placed in a directory on your `PATH`.

#### Linux

Install udev rules to allow non-root HID access:

```bash
sudo cp rules.d/42-cleverswitch.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
# Unplug and replug the receiver
```

#### macOS

On first run, macOS will prompt for **Input Monitoring** permission.

If no prompt appears, grant it manually:

1. Open **System Settings > Privacy & Security > Input Monitoring**.
2. Click the **+** button.
3. Press **Cmd + Shift + G** and paste the path to your binary (e.g., `/your/path/cleverswitch`).

Use `which cleverswitch` to find the path.

---

### Windows

1. Download `cleverswitch.zip` from the [Releases](https://github.com/MikalaiBarysevich/CleverSwitch/releases) page.
2. Extract the archive.
3. Add the location of `cleverswitch.exe` to `PATH` (optional, but preferred).
4. Execute `setup_startup_windows.bat` if you want to run the app at startup.
   If step 3 is skipped, the script and executable must be in the same directory.

---

### Homebrew

Will work on this once this rules for [Homebrew formulae](https://docs.brew.sh/Acceptable-Formulae#niche-or-self-submitted-stuff) will be satisfied:  

> - be known (e.g. GitHub repositories should have >=30 forks, >=30 watchers or >=75 stars)
> - be used by someone other than the author (e.g. someone other than the author submitted the pull request or opened an issue with us or them to add it to Homebrew)

---

### Linux

Will be available later.

---

## Run on Startup

### Windows

1. If you skipped step 3 during installation (or installed from source), place `setup_startup_windows.bat` in the same directory as `cleverswitch.exe`.
2. Run `setup_startup_windows.bat`.

To verify, open Task Manager and look for `cleverswitch.exe` in the **Details** tab.

### Linux

#### Option 1 (preferred)

Use your distro's autostart mechanism (e.g., GNOME Tweaks, KDE Autostart). Add `cleverswitch` as a login/autostart item.

#### Option 2

Use one of the methods listed [here](https://www.baeldung.com/linux/run-script-on-startup).

### macOS

Run the setup script:

```bash
./scripts/setup_startup_mac.sh
```

## Found a Bug?

If you've encountered an issue, please open a [new issue](https://github.com/MikalaiBarysevich/CleverSwitch/issues/new).

## Configuration

Will be available in later releases.

## Hook Scripts

Will be available in later releases.

## Relation to Solaar

CleverSwitch is inspired by [Solaar](https://github.com/pwr-Solaar/Solaar) and uses the same HID++ 2.0 protocol knowledge, but is an independent, minimal implementation. It does not import or depend on Solaar.

## Support the Project

If you find this project useful, consider supporting its development:

- **Credit Card:** [Donate via Boosty](https://boosty.to/mikalaibarysevich)
- **Crypto:**
  - `BTC`: 1HXzgmGZHjLMWrQC8pgYvmcm6afD4idqr7
  - `USDT (TRC20)`: TXpJ3MHcSc144npXLuRbU81gJjD8cwAyzP
