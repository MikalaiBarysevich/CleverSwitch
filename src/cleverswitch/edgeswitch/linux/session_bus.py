from __future__ import annotations

import os
import time
from collections import deque
from collections.abc import Mapping

from jeepney import DBusAddress, HeaderFields, MessageType, new_error, new_method_call, new_method_return
from jeepney.io.blocking import open_dbus_connection

from .edge_bus import CALL, SIGNAL, BusMessage

CALL_TIMEOUT_S = 1.0


def session_address(env: Mapping[str, str]) -> str:
    address = env.get("DBUS_SESSION_BUS_ADDRESS")
    if address:
        return address
    runtime = env.get("XDG_RUNTIME_DIR")
    if not runtime:
        raise OSError("no session bus: DBUS_SESSION_BUS_ADDRESS and XDG_RUNTIME_DIR are unset")
    return f"unix:path={os.path.join(runtime, 'bus')}"


class SessionBus:
    """The session bus through jeepney's blocking connection. Unlike send_and_get_reply, call() keeps every
    message that arrives before its reply, so a peer's call is never dropped."""

    def __init__(self, env: Mapping[str, str] = os.environ, connection=None):
        # The connection is injectable so the reply matching below can be tested without a bus.
        self._conn = connection if connection is not None else open_dbus_connection(session_address(env))
        self._pending: deque = deque()
        self._closed = False

    def fd(self) -> int:
        return self._conn.sock.fileno()

    def call(self, destination, path, interface, member, signature="", body=()) -> tuple:
        message = new_method_call(DBusAddress(path, destination, interface), member, signature or None, tuple(body))
        serial = next(self._conn.outgoing_serial)
        self._conn.send(message, serial=serial)
        deadline = time.monotonic() + CALL_TIMEOUT_S
        while True:
            reply = self._conn.receive(timeout=max(0.0, deadline - time.monotonic()))
            if reply.header.fields.get(HeaderFields.reply_serial) != serial:
                self._pending.append(reply)
                continue
            if reply.header.message_type == MessageType.error:
                name = reply.header.fields.get(HeaderFields.error_name, "error")
                raise OSError(f"{interface}.{member} failed: {name} {reply.body}")
            return reply.body

    def receive(self) -> BusMessage | None:
        if self._pending:
            return _wrap(self._pending.popleft())
        try:
            return _wrap(self._conn.receive(timeout=0))
        except TimeoutError:
            return None

    def reply(self, message: BusMessage) -> None:
        self._conn.send(new_method_return(message.handle))

    def error(self, message: BusMessage, name: str) -> None:
        self._conn.send(new_error(message.handle, name))

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._conn.close()


def _wrap(message) -> BusMessage:
    fields = message.header.fields
    kind = {MessageType.method_call: CALL, MessageType.signal: SIGNAL}.get(message.header.message_type, "")
    return BusMessage(
        kind=kind,
        sender=fields.get(HeaderFields.sender, ""),
        path=fields.get(HeaderFields.path, ""),
        interface=fields.get(HeaderFields.interface, ""),
        member=fields.get(HeaderFields.member, ""),
        body=message.body,
        handle=message,
    )
