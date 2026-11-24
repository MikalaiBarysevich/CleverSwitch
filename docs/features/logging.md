# Logging

CleverSwitch writes a size-rotated log file on every platform:

- **Linux:** `~/.local/state/cleverswitch/cleverswitch.log` (or `$XDG_STATE_HOME/cleverswitch/`). Under systemd the output also goes to the journal: `journalctl --user -u cleverswitch`.
- **macOS:** `~/Library/Logs/CleverSwitch/cleverswitch.log` (also visible in Console.app).
- **Windows:** `%LOCALAPPDATA%\CleverSwitch\Logs\cleverswitch.log`

When the file reaches its size limit it is renamed to `cleverswitch.log.1` (older ones shift to `.2`, `.3`, ...) and a fresh file is started. When run from a terminal, logs are printed there as well. If a second instance is started it logs to the console only. `-v` / `-vv` force DEBUG.

## Configuration

Logging is configured in the `logging:` section of the config file:

```yaml
logging:
  level: INFO          # DEBUG | INFO | WARNING | ERROR | CRITICAL
  file:
    enabled: true      # false: console only
    path: ~/cleverswitch.log
    max_size_mb: 5     # 1..1024
    backup_count: 3    # 1..50
```

The config file lives at `~/.config/cleverswitch/config.yaml` (`%USERPROFILE%\.config\cleverswitch\config.yaml` on Windows) unless `--config` is passed. See [Configuration](../configuration.md) for the full file reference.

## Debug output

`-v` forces DEBUG logging and `-vv` also covers discovery. Stop the installed instance first, so a second daemon does not run alongside it:

- **Linux:** `systemctl --user stop cleverswitch`
- **macOS:** `brew services stop cleverswitch` (Homebrew), or `launchctl unload ~/Library/LaunchAgents/com.user.cleverswitch.plist` (binary or source install)
- **Windows:** end `cleverswitch.exe` in Task Manager

Run `cleverswitch -v` from a terminal, then start the service again when you are done.

## Reporting a bug

When reporting a bug, please attach this log file — and run `cleverswitch -v` while reproducing the problem if you can (see [Debug output](#debug-output)). It makes a fix much faster.
