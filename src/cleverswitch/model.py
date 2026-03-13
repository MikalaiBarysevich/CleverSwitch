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
class LogiProduct:
    """Everything needed to talk to one device."""

    slot: int  # 1-6 for receiver-paired, 0xFF for Bluetooth direct
    change_host_feat_idx: int
    divert_feat_idx: int | None
    role: str  # "keyboard" or "mouse"
    name: str
    connected: bool = False


@dataclass
class ProductEntry:
    """Entry in the shared product registry — everything needed to send CHANGE_HOST."""

    transport: HIDTransport
    devnumber: int  # slot 1-6 for receiver, 0xFF for BT
    change_host_feat_idx: int
    divert_feat_idx: int | None
    role: str
    name: str
