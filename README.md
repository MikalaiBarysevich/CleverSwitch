# CleverSwitch

A small, headless, cross-platform daemon that synchronizes host switching between Logitech keyboard and mouse.
When you press the Easy-Switch button on the keyboard, CleverSwitch detects it and immediately sends the same host-switch command to the mouse — so both devices land on the same host simultaneously.

- Runs alongside Logi Options+ or Solaar without conflicts.
- Must be installed on every host you plan to switch from.
- Currently supports connections via Logitech receivers and Bluetooth.
- Tested with `MX Keys` and `MX Master 3` on Linux, macOS, and Windows.

> CleverSwitch does not override device firmware. It acts as a forwarder, which means there is a small delay
> after reconnection. If you switch back immediately after arriving from another host, the devices may not
> switch together — CleverSwitch needs a moment to set everything up after reconnection.
> Especially on Bluetooth. But it mostly depends on the BT version.

## Installation

### macOS

1. Clone the repository (or download the sources archive from [Releases](https://github.com/MikalaiBarysevich/CleverSwitch/releases)).
2. Open Terminal and navigate to the project folder.
3. Run:
```bash
chmod +x scripts/mac/setup.sh
./scripts/mac/setup.sh
```

The setup script will install Homebrew (if needed), Python, hidapi, and CleverSwitch itself.
It will also ask whether you want CleverSwitch to start automatically on login.

On first run, macOS will prompt for **Input Monitoring** permission.
If no prompt appears, grant it manually:

1. Open **System Settings > Privacy & Security > Input Monitoring**.
2. Click the **+** button.
3. Press **Cmd + Shift + G** and paste the path to your binary (e.g., `/your/path/cleverswitch`).

Use `which cleverswitch` to find the path.

### Windows

1. Download `cleverswitch.zip` from the [Releases](https://github.com/MikalaiBarysevich/CleverSwitch/releases) page.
2. Extract the archive.
3. Add the location of `cleverswitch.exe` to `PATH` (optional, but preferred).
4. Run `setup_startup_windows.bat` if you want the app to start automatically.
   If step 3 is skipped, the script and executable must be in the same directory.

### Linux

1. Clone the repository (or download the sources archive from [Releases](https://github.com/MikalaiBarysevich/CleverSwitch/releases)).
2. Open a terminal and navigate to the project folder.
3. Run:
```bash
chmod +x scripts/linux/setup_linux.sh
./scripts/linux/setup_linux.sh
```

The setup script will check for Python 3 and hidapi, install CleverSwitch, set up udev rules for non-root HID access, and optionally create an autostart entry.

### From Sources

_Requires Python >=3.10 on PATH._

1. Clone the repository.
2. Install:
```bash
pip install .
```
3. Run:
```bash
cleverswitch
```

**Windows note:** The [hidapi DLL](https://github.com/libusb/hidapi/releases) must be downloaded manually and placed in a directory on your `PATH`.

**Linux note:** Install udev rules to allow non-root HID access:
```bash
sudo cp rules.d/42-cleverswitch.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
# Unplug and replug the receiver
```

**macOS note:** On first run, macOS will prompt for Input Monitoring permission (see macOS section above).

### Homebrew

Will be available once the [Homebrew formulae criteria](https://docs.brew.sh/Acceptable-Formulae#niche-or-self-submitted-stuff) are met:

> - be known (e.g. GitHub repositories should have >=30 forks, >=30 watchers or >=75 stars)
> - be used by someone other than the author

## Run on Startup

### macOS

Handled by `setup_mac.sh` during installation. To set up separately:
```bash
chmod +x scripts/mac/setup_startup.sh
./scripts/mac/setup_startup.sh
```

### Windows

1. Place `setup_startup_windows.bat` in the same directory as `cleverswitch.exe` (unless it's already on `PATH`).
2. Run `setup_startup_windows.bat`.

To verify, open Task Manager and look for `cleverswitch.exe` in the **Details** tab.

### Linux

Handled by `setup_linux.sh` during installation. To set up separately, use your distro's autostart mechanism (e.g., GNOME Tweaks, KDE Autostart) or see [other methods](https://www.baeldung.com/linux/run-script-on-startup).

## Uninstall

### macOS

```bash
chmod +x scripts/mac/uninstall.sh
./scripts/mac/uninstall.sh
```

This stops and removes the launch agent (if configured) and uninstalls the CleverSwitch package.

### Linux

```bash
chmod +x scripts/linux/uninstall_linux.sh
./scripts/linux/uninstall_linux.sh
```

This removes the autostart entry, uninstalls the CleverSwitch package, and optionally removes udev rules.

### Windows

1. Delete the `cleverswitch` folder.
2. Remove the startup entry: open Task Manager > **Startup** tab, find `cleverswitch`, and disable/delete it.

### From Sources

```bash
pip uninstall cleverswitch
```

## Configuration

Will be available in later releases.

## Hook Scripts

Will be available in later releases.

## Relation to Solaar

CleverSwitch is inspired by [Solaar](https://github.com/pwr-Solaar/Solaar) and uses the same HID++ 2.0 protocol knowledge, but is an independent, minimal implementation. It does not import or depend on Solaar.

## Found a Bug?

Please open a [new issue](https://github.com/MikalaiBarysevich/CleverSwitch/issues/new).

## Support the Project

If you find this project useful, consider supporting its development:

- **Credit Card:** [Donate via Boosty](https://boosty.to/mikalaibarysevich)
- **Crypto:**
  - `BTC`: 1HXzgmGZHjLMWrQC8pgYvmcm6afD4idqr7
  - `USDT (TRC20)`: TXpJ3MHcSc144npXLuRbU81gJjD8cwAyzP
