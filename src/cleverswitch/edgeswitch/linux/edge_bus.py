from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable
from typing import Any, Protocol

from ...errors.errors import EdgeSwitchError
from ...model.config.edge import Edge
from ...model.config.modifier import Modifier
from ..edge_sink import EdgeSink

log = logging.getLogger(__name__)

BUS_NAME = "io.github.mikalaibarysevich.CleverSwitch"
OBJECT_PATH = "/io/github/mikalaibarysevich/CleverSwitch"
INTERFACE = f"{BUS_NAME}.EdgeSwitch"

DBUS = "org.freedesktop.DBus"
DBUS_PATH = "/org/freedesktop/DBus"
ACCESS_DENIED = "org.freedesktop.DBus.Error.AccessDenied"
UNKNOWN_METHOD = "org.freedesktop.DBus.Error.UnknownMethod"
_DO_NOT_QUEUE = 4
_PRIMARY_OWNER = 1

EDGE_BITS = {Edge.LEFT: 1, Edge.RIGHT: 2, Edge.TOP: 4, Edge.BOTTOM: 8}

CALL = "call"
SIGNAL = "signal"


@dataclasses.dataclass(frozen=True)
class BusMessage:
    kind: str  # CALL, SIGNAL or anything else, which is ignored
    sender: str = ""
    path: str = ""
    interface: str = ""
    member: str = ""
    body: tuple = ()
    handle: Any = None  # the transport's own message, needed to reply


class Bus(Protocol):
    # One session-bus connection; every method runs on the backend thread.
    def fd(self) -> int: ...

    # A blocking method call; raises OSError on an error reply or timeout. Messages that arrive meanwhile are
    # kept for receive().
    def call(self, destination: str, path: str, interface: str, member: str, signature: str = "", body=()) -> tuple: ...

    # The next pending message, or None without blocking.
    def receive(self) -> BusMessage | None: ...

    def reply(self, message: BusMessage) -> None: ...

    def error(self, message: BusMessage, name: str) -> None: ...

    def close(self) -> None: ...


def dbus_call(bus: Bus, member: str, signature: str = "", *body) -> tuple:
    return bus.call(DBUS, DBUS_PATH, DBUS, member, signature, body)


def has_owner(bus: Bus, name: str) -> bool:
    return bool(dbus_call(bus, "NameHasOwner", "s", name)[0])


def decode_edges(mask: Any) -> frozenset[Edge]:
    if isinstance(mask, bool) or not isinstance(mask, int | float):
        raise ValueError(f"edge mask {mask!r}")
    bits = int(mask)
    return frozenset(edge for edge, bit in EDGE_BITS.items() if bits & bit)


StateDecoder = Callable[[Any], tuple[Modifier, bool]]


class EdgeBus:
    """CleverSwitch's end of the edge-report channel: it owns BUS_NAME and takes calls only from the
    compositor peer (KWin or GNOME Shell), identified by the unique name that owned `peer` at start. The bus
    sets the sender field itself, so other session clients cannot pose as the peer. The peer going away
    raises OSError out of drain(), which ends the loop until the next revive."""

    def __init__(self, bus: Bus, peer: str, decode_state: StateDecoder | None = None, matches: tuple[str, ...] = ()):
        self._bus = bus
        self._peer = peer
        self._decode_state = decode_state
        # Every watch is in place before the owner is read and before RequestName, which is what the peer
        # reacts to. Subscribing first means an owner change between the two calls is either seen as a signal
        # or already reflected in the owner we read, never missed.
        for rule in (f"type='signal',sender='{DBUS}',member='NameOwnerChanged',arg0='{peer}'", *matches):
            self.add_match(rule)
        self._peer_owner = str(dbus_call(bus, "GetNameOwner", "s", peer)[0])
        if dbus_call(bus, "RequestName", "su", BUS_NAME, _DO_NOT_QUEUE)[0] != _PRIMARY_OWNER:
            raise EdgeSwitchError("another CleverSwitch is already watching screen edges")

    @property
    def bus(self) -> Bus:
        return self._bus

    def fd(self) -> int:
        return self._bus.fd()

    def add_match(self, rule: str) -> None:
        dbus_call(self._bus, "AddMatch", "s", rule)

    def drain(self, sink: EdgeSink, on_signal: Callable[[BusMessage], None] | None = None) -> None:
        while (message := self._bus.receive()) is not None:
            if message.kind == CALL:
                self._on_call(message, sink)
            elif message.kind == SIGNAL:
                self._on_signal(message, on_signal)

    def close(self) -> None:
        self._bus.close()

    def _on_call(self, message: BusMessage, sink: EdgeSink) -> None:
        if message.path != OBJECT_PATH or message.interface != INTERFACE:
            self._bus.error(message, UNKNOWN_METHOD)
            return
        if message.sender != self._peer_owner:
            log.debug(f"Edge switch ignores {message.member} from {message.sender}")
            self._bus.error(message, ACCESS_DENIED)
            return
        try:
            if message.member == "Edges":
                edges = decode_edges(message.body[0])
                self._bus.reply(message)
                sink.on_edges(edges)
            elif message.member == "State" and self._decode_state is not None:
                state = self._decode_state(message.body[0])
                self._bus.reply(message)
                sink.on_state(*state)
            else:
                self._bus.error(message, UNKNOWN_METHOD)
        except (IndexError, ValueError, TypeError):
            log.debug(f"Edge switch ignores a malformed {message.member} call")
            self._bus.error(message, UNKNOWN_METHOD)

    def _on_signal(self, message: BusMessage, on_signal: Callable[[BusMessage], None] | None) -> None:
        # The bus daemon sets sender itself, so only it can report an owner change; without this a spoofed
        # signal delivered through a permissive extra match rule could take the loop down.
        if (
            message.member == "NameOwnerChanged"
            and message.interface == DBUS
            and message.sender == DBUS
            and len(message.body) == 3
        ):
            name, _old, new = message.body
            if name == self._peer and new != self._peer_owner:
                raise OSError(f"{self._peer} went away")
            return
        if on_signal is not None:
            on_signal(message)
