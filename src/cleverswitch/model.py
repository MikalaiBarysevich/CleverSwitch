from dataclasses import dataclass

from .hidpp.transport import HIDTransport


@dataclass
class BaseEvent:
    slot: int


@dataclass
class HostChangeEvent(BaseEvent):
    """Diverted Easy-Switch event from device."""

    target_host: int


@dataclass
class ConnectionEvent(BaseEvent):
    slot: int


@dataclass
class ExternalUndivertEvent(BaseEvent):
    target_host_cid: int


@dataclass
class DisconnectEvent(BaseEvent):
    """Disconnect notification for a receiver-paired device (SHORT report, HID_DEVICE_PAIRING)."""


@dataclass
class LogiProduct:
    """Everything needed to talk to one device."""

    slot: int  # 1-6 for receiver-paired, 0xFF for Bluetooth direct
    change_host_feat_idx: int
    divert_feat_idx: int | None
    role: str  # "keyboard" or "mouse"
    name: str
    connected: bool = False
    # Fields for non-divertable keyboard host tracking (x1814 / x1815)
    paired_hosts: tuple[int, ...] | None = None
    current_host: int | None = None
    hosts_info_feat_idx: int | None = None


@dataclass(frozen=True)
class CachedBTDevice:
    """Cached BT device identity — stable across reconnects.

    Keyed by PID so that when the same physical device reconnects (new HID path,
    same PID) the full HID++ probe can be skipped and identity restored instantly.
    """

    pid: int
    role: str
    name: str
    change_host_feat_idx: int
    divert_feat_idx: int | None
    hosts_info_feat_idx: int | None


@dataclass
class ProductEntry:
    """Entry in the shared product registry — everything needed to send CHANGE_HOST."""

    transport: HIDTransport
    devnumber: int  # slot 1-6 for receiver, 0xFF for BT
    change_host_feat_idx: int
    divert_feat_idx: int | None
    role: str
    name: str
