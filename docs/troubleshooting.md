# Troubleshooting

## Start with the log

Run `cleverswitch -v` and reproduce the problem. Stop the installed service first (see [Debug output](features/logging.md#debug-output)) so two daemons do not run together. The debug log names the device it talks to and the command it sends. Log file locations are listed in [Logging](features/logging.md) — attach it when you report a bug.

## Nothing switches

- CleverSwitch must run on the host you are switching **from**. Install it on every host in your Easy-Switch rotation.
- Press an Easy-Switch key and look for `Sending host change to 'MX Master 3' -> host 2` in the log. If the line is missing, the keyboard press was not seen or the device was not discovered — see the next section.
- After a device reconnects, give CleverSwitch a moment to set it up. Switching again immediately can leave the devices on different hosts.
- Hooks are keyboard-only by default. If a hook does not fire, set `hooks.fire_for_all_devices: true` or a per-hook override — see [Hooks](features/hooks.md).
- Run one instance per machine. A second instance is not coordinated with the first and logs to the console only; on KDE and GNOME edge switch refuses a second backend, but elsewhere both could send switches.

## A device is not detected

- **Linux:** replug the receiver once after installing or updating the udev rule, so it takes effect.
- **Windows:** for a source install, the [hidapi DLL](https://github.com/libusb/hidapi/releases) must be in a directory on `PATH`.
- **macOS:** grant *Input Monitoring* in System Settings → Privacy & Security → Input Monitoring.
- Clear the device cache with `cleverswitch --clear-cache`, then restart CleverSwitch. This only removes cached discovery data; devices are discovered again on the next connection.
- Check the installation notes for your platform: [Installation](installation.md).

## Edge switch does nothing

Edge switch has its own diagnostics and platform requirements: see [If nothing happens](features/edge-switch.md#if-nothing-happens) in the edge switch guide.

## Reporting a bug

Open a [new issue](https://github.com/MikalaiBarysevich/CleverSwitch/issues/new?template=BUG.yml) and attach the log file from [Logging](features/logging.md). The debug log from `cleverswitch -v` is the most useful thing you can include.
