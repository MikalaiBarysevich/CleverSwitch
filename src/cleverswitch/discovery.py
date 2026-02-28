"""Device discovery across all connection types.

Finds keyboard and mouse by scanning:
  1. Bolt / Unifying receivers — reads pairing register to get wpid for each slot
  2. Bluetooth — enumerates HID devices by Bluetooth product ID

Returns a Setup object describing how to talk to each device.
"""

from __future__ import annotations

import dataclasses
import logging

from .config import Config
from .errors import DeviceNotFound
from .hidpp.constants import (
    DEVICE_RECEIVER,
    FEATURE_CHANGE_HOST,
    FEATURE_REPROG_CONTROLS_V4,
)
from .hidpp.protocol import (
    get_change_host_info,
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
    """Resolved device contexts for keyboard and mouse."""
    keyboard: DeviceContext
    mouse: DeviceContext

    def unique_transports(self) -> list[HIDTransport]:
        """Unique transports needed (de-duplicated by object identity)."""
        seen: dict[int, HIDTransport] = {}
        for ctx in (self.keyboard, self.mouse):
            seen.setdefault(id(ctx.transport), ctx.transport)
        return list(seen.values())


# ── Public entry point ────────────────────────────────────────────────────────

def discover(cfg: Config) -> Setup:
    """Scan all connection types and return a Setup for the configured devices.

    Raises DeviceNotFound if either device cannot be located.
    Raises FeatureNotSupported if CHANGE_HOST (0x1814) is missing.
    """
    log.info("Starting device discovery…")
    contexts: dict[str, DeviceContext] = {}

    _scan_receivers(cfg, contexts)
    if len(contexts) < 2:
        _scan_bluetooth(cfg, contexts)

    missing = [role for role in ("keyboard", "mouse") if role not in contexts]
    if missing:
        for role in missing:
            dev_cfg = cfg.keyboard if role == "keyboard" else cfg.mouse
            raise DeviceNotFound(role, dev_cfg.wpid)

    setup = Setup(keyboard=contexts["keyboard"], mouse=contexts["mouse"])
    log.info(
        "Ready — keyboard: dev=%d feat=%d | mouse: dev=%d feat=%d",
        setup.keyboard.devnumber, setup.keyboard.change_host_feat_idx,
        setup.mouse.devnumber, setup.mouse.change_host_feat_idx,
    )
    return setup


# ── Receiver scanning ─────────────────────────────────────────────────────────

def _scan_receivers(cfg: Config, contexts: dict[str, DeviceContext]) -> None:
    """Scan Bolt/Unifying receivers for configured devices."""
    transports = find_receiver_transports()
    if not transports:
        log.info("No Bolt/Unifying receivers found")
        return

    for transport in transports:
        _scan_one_receiver(transport, cfg, contexts)
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
        cfg: Config,
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

        role = _role_for_wpid(wpid, cfg)
        if role is None or role in contexts:
            continue

        dev_cfg = cfg.keyboard if role == "keyboard" else cfg.mouse

        # Override slot if device_index is pinned in config
        devnumber = dev_cfg.device_index if dev_cfg.device_index is not None else slot

        ctx = _make_context(transport, devnumber, long_msg=False, role=role, name=dev_cfg.name, wpid=wpid)
        if ctx:
            contexts[role] = ctx


def _role_for_wpid(wpid: int, cfg: Config) -> str | None:
    if cfg.keyboard.wpid == wpid:
        return "keyboard"
    if cfg.mouse.wpid == wpid:
        return "mouse"
    return None


# ── Bluetooth scanning ────────────────────────────────────────────────────────

def _scan_bluetooth(cfg: Config, contexts: dict[str, DeviceContext]) -> None:
    """Scan for Logitech Bluetooth HID++ devices."""
    bt_devices = find_bluetooth_transports()
    if not bt_devices:
        log.info("No Bluetooth devices found")
        return

    for transport, btid in bt_devices:
        if len(contexts) == 2:
            transport.close()
            continue

        role = _role_for_btid(btid, cfg)
        if role is None or role in contexts:
            transport.close()
            continue

        dev_cfg = cfg.keyboard if role == "keyboard" else cfg.mouse

        # Bluetooth devices use 0xFF as device number in messages
        ctx = _make_context(transport, DEVICE_RECEIVER, long_msg=True, role=role, name=dev_cfg.name, wpid=None)
        if ctx:
            contexts[role] = ctx
        else:
            transport.close()


def _role_for_btid(btid: int, cfg: Config) -> str | None:
    if cfg.keyboard.btid == btid:
        return "keyboard"
    if cfg.mouse.btid == btid:
        return "mouse"
    return None


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
            name, devnumber, transport.kind,
        )
        return None
    log.debug("%s (dev=0x%02X, %s) found CHANGE_HOST (0x1814) idx — %s",
              name, devnumber, transport.kind, feat_idx)

    feat_idx_rep = None
    if role == "keyboard":
        feat_idx_rep = resolve_feature_index(transport, devnumber, FEATURE_REPROG_CONTROLS_V4, long=long_msg)
        log.debug("feat_idx_rep=%s", feat_idx_rep)
        if feat_idx_rep is None:
            log.warning(
                "%s (dev=0x%02X, %s) does not support FEATURE_REPROG_CONTROLS_V4 (0x1B04) — skipping",
                name, devnumber, transport.kind,
            )
            return None
        log.debug("%s (dev=0x%02X, %s) found FEATURE_REPROG_CONTROLS_V4 (0x1B04) idx — %s",
                  name, devnumber, transport.kind, feat_idx_rep)

    log.info("%s found: transport=%s dev=0x%02X", name, transport.kind, devnumber)

    info = get_change_host_info(transport, devnumber, feat_idx, long=long_msg)
    if info:
        num_hosts, current_host = info
        log.info("%s: %d hosts available, currently on host %d", name, num_hosts, current_host + 1)

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
