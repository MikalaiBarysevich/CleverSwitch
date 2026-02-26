"""Relay a host-switch command from keyboard to mouse."""

from __future__ import annotations

import logging

from .discovery import DeviceContext
from .hidpp.protocol import send_change_host

log = logging.getLogger(__name__)


def relay_switch(keyboard: DeviceContext, mouse: DeviceContext, target_host: int) -> None:
    """Send CHANGE_HOST to both keyboard and mouse.

    With Easy-Switch keys diverted, the keyboard has NOT switched yet —
    CleverSwitch handles the switch explicitly for both devices.

    :param target_host: 0-based host index (0, 1, or 2)
    """
    log.info("Switching both devices to host %d", target_host + 1)
    send_change_host(
        keyboard.transport,
        keyboard.devnumber,
        keyboard.change_host_feat_idx,
        target_host,
        long=keyboard.long_msg,
    )
    send_change_host(
        mouse.transport,
        mouse.devnumber,
        mouse.change_host_feat_idx,
        target_host,
        long=mouse.long_msg,
    )
