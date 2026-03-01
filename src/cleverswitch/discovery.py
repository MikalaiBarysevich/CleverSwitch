"""Device discovery across all connection types.

Finds keyboard and mouse by scanning:
  1. Bolt / Unifying receivers — reads pairing register to get wpid for each slot
  2. Bluetooth — enumerates HID devices by Bluetooth product ID

Returns a Setup object describing how to talk to each device.
"""

from __future__ import annotations

import dataclasses
import logging

from .hidpp.constants import (
    DEVICE_RECEIVER,
    DEVICE_TYPE_KEYBOARD,
    DEVICE_TYPE_MOUSE,
    DEVICE_TYPE_TRACKBALL,
    DEVICE_TYPE_TRACKPAD,
    FEATURE_CHANGE_HOST,
    FEATURE_DEVICE_TYPE_AND_NAME,
    FEATURE_REPROG_CONTROLS_V4,
)
from .hidpp.protocol import (
    get_change_host_info,
    get_device_name,
    get_device_type,
    read_pairing_wpid,
    resolve_feature_index,
)
from .hidpp.transport import HIDTransport, find_bluetooth_transports, find_receiver_transports

log = logging.getLogger(__name__)


@dataclasses.dataclass
class DeviceContext:
    """Everything needed to talk to one device."""

    transport: HIDTransport
    devnumber: int  # 1-6 for receiver-paired, 0xFF for Bluetooth direct
    change_host_feat_idx: int
    divert_feat_idx: int | None
    long_msg: bool  # True for Bluetooth (always long messages)
    role: str  # "keyboard" or "mouse"
    name: str
    wpid: int | None
    reprog_feat_idx: int | None = dataclasses.field(default=None)
    diverted_cids: list = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class Setup:
    """Resolved device contexts for discovered devices."""

    devices: list[DeviceContext]


# ── Public entry point ────────────────────────────────────────────────────────


def discover() -> Setup | None:
    """Scan all connection types and return a Setup for the configured devices.

    Raises DeviceNotFound if either device cannot be located.
    Raises FeatureNotSupported if CHANGE_HOST (0x1814) is missing.
    """
    log.info("Starting device discovery…")
    contexts: dict[str, DeviceContext] = {}

    _scan_receivers(contexts)
    if len(contexts) < 2:
        _scan_bluetooth(contexts)

    missing = [role for role in ("keyboard", "mouse") if role not in contexts]
    if missing:
        return None

    setup = Setup(devices=list(contexts.values()))
    return setup


# ── Device-type auto-discovery ────────────────────────────────────────────────

_MOUSE_DEVICE_TYPES = frozenset((DEVICE_TYPE_MOUSE, DEVICE_TYPE_TRACKBALL, DEVICE_TYPE_TRACKPAD))


def _device_type_to_role(device_type: int | None) -> str | None:
    """Map an x0005 deviceType value to 'keyboard', 'mouse', or None."""
    if device_type == DEVICE_TYPE_KEYBOARD:
        return "keyboard"
    if device_type in _MOUSE_DEVICE_TYPES:
        return "mouse"
    return None


def _query_device_info(transport: HIDTransport, devnumber: int, long: bool = False) -> tuple[str, str] | None:
    """Query role and marketing name via x0005 DEVICE_TYPE_AND_NAME.

    Returns (role, name) where role is 'keyboard' or 'mouse'.
    Falls back to role as name if getDeviceName fails.
    Returns None if the feature is absent or device type is unrecognised.
    """
    feat_idx = resolve_feature_index(transport, devnumber, FEATURE_DEVICE_TYPE_AND_NAME, long=long)
    if feat_idx is None:
        return None
    device_type = get_device_type(transport, devnumber, feat_idx, long=long)
    role = _device_type_to_role(device_type)
    if role is None:
        return None
    name = get_device_name(transport, devnumber, feat_idx, long=long) or role
    return role, name


# ── Receiver scanning ─────────────────────────────────────────────────────────


def _scan_receivers(contexts: dict[str, DeviceContext]) -> None:
    """Scan Bolt/Unifying receivers for configured devices."""
    transports = find_receiver_transports()
    if not transports:
        log.info("No Bolt/Unifying receivers found")
        return

    for transport in transports:
        _scan_one_receiver(transport, contexts)
        if len(contexts) == 2:
            # Close any receiver transports we opened but don't need
            for t in transports:
                if t is not transport and id(t) not in {id(ctx.transport) for ctx in contexts.values()}:
                    t.close()
            return

    # Close transports that yielded no devices
    for transport in transports:
        if id(transport) not in {id(ctx.transport) for ctx in contexts.values()}:
            transport.close()


def _scan_one_receiver(
    transport: HIDTransport,
    contexts: dict[str, DeviceContext],
) -> None:
    """Scan all pairing slots in one receiver. Populates *contexts* in-place."""
    max_slot = 6
    for slot in range(1, max_slot + 1):
        # Check if we already found both devices
        if len(contexts) == 2:
            return

        wpid = read_pairing_wpid(transport, slot, transport.kind)
        if wpid is None:
            continue

        log.debug("Receiver slot %d: wpid=0x%04X", slot, wpid)

        info = _query_device_info(transport, slot, long=False)
        if info is None or info[0] in contexts:
            continue

        role, name = info
        ctx = _make_context(transport, slot, long_msg=False, role=role, name=name, wpid=wpid)
        if ctx:
            contexts[role] = ctx


# ── Bluetooth scanning ────────────────────────────────────────────────────────


def _scan_bluetooth(contexts: dict[str, DeviceContext]) -> None:
    """Scan for Logitech Bluetooth HID++ devices."""
    bt_devices = find_bluetooth_transports()
    if not bt_devices:
        log.info("No Bluetooth devices found")
        return

    for transport, _btid in bt_devices:
        if len(contexts) == 2:
            transport.close()
            continue

        info = _query_device_info(transport, DEVICE_RECEIVER, long=True)
        if info is None or info[0] in contexts:
            transport.close()
            continue

        role, name = info
        ctx = _make_context(transport, DEVICE_RECEIVER, long_msg=True, role=role, name=name, wpid=None)
        if ctx:
            contexts[role] = ctx
        else:
            transport.close()


# ── Context creation ──────────────────────────────────────────────────────────


def _make_context(
    transport: HIDTransport,
    devnumber: int,
    long_msg: bool,
    role: str,
    name: str,
    wpid: int | None,
) -> DeviceContext | None:
    """Resolve CHANGE_HOST feature index and build a DeviceContext.

    Returns None if CHANGE_HOST is not supported (logs a warning).
    Raises FeatureNotSupported if it was expected but missing.
    """
    feat_idx = resolve_feature_index(transport, devnumber, FEATURE_CHANGE_HOST, long=long_msg)
    if feat_idx is None:
        log.warning(
            "%s (dev=0x%02X, %s) does not support CHANGE_HOST (0x1814) — skipping",
            role,
            devnumber,
            transport.kind,
        )
        return None
    log.debug(
        "%s (dev=0x%02X, %s) found CHANGE_HOST (0x1814) idx — %s",
        role,
        devnumber,
        transport.kind,
        feat_idx,
    )

    feat_idx_rep = None
    if role == "keyboard":
        feat_idx_rep = resolve_feature_index(transport, devnumber, FEATURE_REPROG_CONTROLS_V4, long=long_msg)
        log.debug("feat_idx_rep=%s", feat_idx_rep)
        if feat_idx_rep is None:
            log.warning(
                "%s (dev=0x%02X, %s) does not support FEATURE_REPROG_CONTROLS_V4 (0x1B04) - skipping",
                role,
                devnumber,
                transport.kind,
            )
            return None
        log.debug(
            "%s (dev=0x%02X, %s) found FEATURE_REPROG_CONTROLS_V4 (0x1B04) idx — %s",
            role,
            devnumber,
            transport.kind,
            feat_idx_rep,
        )

    info = get_change_host_info(transport, devnumber, feat_idx, long=long_msg)
    if info:
        num_hosts, current_host = info
        log.info(
            "'%s' found: transport=%s, dev=0x%02X, %d hosts available, currently on host %d",
            name,
            transport.kind,
            devnumber,
            num_hosts,
            current_host + 1,
        )

    ctx = DeviceContext(
        transport=transport,
        devnumber=devnumber,
        change_host_feat_idx=feat_idx,
        divert_feat_idx=feat_idx_rep,
        long_msg=long_msg,
        role=role,
        name=name,
        wpid=wpid,
    )
    return ctx
