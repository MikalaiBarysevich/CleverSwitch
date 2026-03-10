"""Platform-specific prerequisite checks and guidance."""

from __future__ import annotations

import logging
import os
import platform

log = logging.getLogger(__name__)

_SYSTEM = platform.system()


def check() -> None:
    """Run platform-specific checks and log actionable warnings."""
    if _SYSTEM == "Linux":
        _check_linux()
    elif _SYSTEM == "Darwin":
        _check_macos()
    # Windows needs no special setup


def _check_linux() -> None:
    """Warn if udev rules are not installed."""
    rule_name = "42-cleverswitch.rules"
    udev_dirs = [
        "/etc/udev/rules.d",
        "/run/udev/rules.d",
        "/lib/udev/rules.d",
    ]
    for d in udev_dirs:
        if os.path.exists(os.path.join(d, rule_name)):
            log.debug("udev rule found in %s", d)
            return

    log.warning(
        "udev rule not found — you may get a PermissionError when opening the receiver.\n"
        "  To fix:\n"
        "    sudo cp rules.d/42-cleverswitch.rules /etc/udev/rules.d/\n"
        "    sudo udevadm control --reload-rules && sudo udevadm trigger\n"
        "  Then unplug and replug the Bolt/Unifying receiver."
    )


def _check_macos() -> None:
    log.info(
        "macOS: if CleverSwitch cannot open the receiver, grant Input Monitoring permission:\n"
        "  System Settings → Privacy & Security → Input Monitoring → add this terminal / app"
    )
