from dataclasses import dataclass
from typing import Generic, TypeVar

from cleverswitch.hidpp.transport import HIDTransport


@dataclass
class BaseEvent:
    slot: int


@dataclass
class HostChangeEvent(BaseEvent):
    """Diverted Easy-Switch event from device."""

    target_host: int


@dataclass
class DjConnectionEvent(BaseEvent):
    connection_status: int  # 0 - connected, 1 - disconnected


@dataclass
class HidConnectionEvent(BaseEvent):
    slot: int


@dataclass
class LogiProduct:
    """Everything needed to talk to one device."""

    slot: int  # 1-6 for receiver-paired, 0xFF for Bluetooth direct
    change_host_feat_idx: int
    divert_feat_idx: int | None
    role: str  # "keyboard" or "mouse"
    name: str
    connected: bool = False


T = TypeVar("T", bound="BaseEvent")


@dataclass
class EventProcessorArguments(Generic[T]):
    products: dict[int, LogiProduct]
    transport: HIDTransport
    event: T
