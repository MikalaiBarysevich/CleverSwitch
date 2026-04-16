# Installation

## Updating to a newer version

**Pre-built binary:** download the new release archive and run the installer again — it will overwrite the existing binary. No need to uninstall first.

**Installed from source:** pull the latest changes and reinstall:
```bash
git pull
pip install .
```

---

## macOS

### Option 1: Pre-built binary (recommended)

1. Download `cleverswitch_macOS.tar.gz` from the [Releases](https://github.com/MikalaiBarysevich/CleverSwitch/releases) page.
2. Double-click the downloaded file to extract it — a `cleverswitch_macOS` folder will appear.
3. Open the folder and double-click **`install.command`**.
   A Terminal window will open and guide you through the setup, including an option to launch CleverSwitch automatically on login.

On first run, macOS will prompt for **Input Monitoring** permission.
If no prompt appears, grant it manually:

1. Open **System Settings > Privacy & Security > Input Monitoring**.
2. Click the **+** button.
3. Press **Cmd + Shift + G**, paste `~/.local/bin/cleverswitch`, and click Open.

### Option 2: From source

1. Clone the repository.
2. Open Terminal and navigate to the project folder.
3. Run:
```bash
chmod +x scripts/mac/install_from_sources.sh
./scripts/mac/install_from_sources.sh
```

The script installs Homebrew (if needed), Python, and CleverSwitch via pip. It also offers to set up launch-at-login.

## Windows

### Option 1: Pre-built binary (recommended)

1. Download `cleverswitch_windows_x64.zip` from the [Releases](https://github.com/MikalaiBarysevich/CleverSwitch/releases) page.
2. Right-click the downloaded file and choose **Extract All**, then open the extracted folder.
3. Double-click **`install.bat`**.
   The installer will copy `cleverswitch.exe` to your user programs folder, add it to your PATH, and offer to set up startup.

> If Windows shows a security prompt, click **Run anyway** (the file is safe — Windows warns about unrecognised publishers by default).

### Option 2: From source

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

## Linux

### Option 1: Pre-built binary (recommended)

1. Download `cleverswitch_linux.tar.gz` from the [Releases](https://github.com/MikalaiBarysevich/CleverSwitch/releases) page.
2. Extract the archive — most desktop environments let you right-click and choose **Extract Here**.
3. Open a terminal inside the extracted folder and run:
```bash
chmod +x install.sh && ./install.sh
```

The installer copies the binary to `~/.local/bin/`, checks that the directory is on your PATH, installs udev rules for non-root HID access (with your confirmation), and offers to set up autostart.

### Option 2: From source

1. Clone the repository.
2. Open a terminal and navigate to the project folder.
3. Run:
```bash
chmod +x scripts/linux/install_from_sources.sh
./scripts/linux/install_from_sources.sh
```

The script checks for Python 3, installs CleverSwitch via pip, sets up udev rules, and optionally creates an autostart entry.

## Run on Startup

### macOS

Handled by `install.command` or `install_from_sources.sh` during installation. To set up separately:
```bash
chmod +x scripts/mac/setup_startup.command
./scripts/mac/setup_startup.command
```

### Windows

Handled by `install.ps1` during installation. To set up separately, run `setup_startup_windows.bat` from the folder containing `cleverswitch.exe`.

To verify, open Task Manager and look for `cleverswitch.exe` in the **Details** tab.

### Linux

Handled by `install.sh` or `install_from_sources.sh` during installation. To set up separately, use your distro's autostart mechanism (e.g., GNOME Tweaks, KDE Autostart) or see [other methods](https://www.baeldung.com/linux/run-script-on-startup).

## Uninstall

### macOS

Open the `cleverswitch_macOS` folder and double-click **`uninstall.command`**. This stops and removes the launch agent (if configured) and removes the CleverSwitch binary.

### Linux

```bash
chmod +x scripts/linux/uninstall.sh
./scripts/linux/uninstall.sh
```

This removes the autostart entry, removes the binary from `~/.local/bin/`, uninstalls the CleverSwitch pip package if present, and optionally removes udev rules.

### Windows

Double-click **`uninstall.bat`** (included in the release archive).

This removes the startup entry, removes `%LOCALAPPDATA%\Programs\CleverSwitch\` from your PATH, and deletes the install directory.
