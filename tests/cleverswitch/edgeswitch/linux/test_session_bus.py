import itertools
from types import SimpleNamespace

import pytest

pytest.importorskip("jeepney")

from jeepney import HeaderFields, MessageType  # noqa: E402

from cleverswitch.edgeswitch.linux.session_bus import SessionBus, session_address  # noqa: E402


def test_session_address_prefers_the_environment():
    assert session_address({"DBUS_SESSION_BUS_ADDRESS": "unix:path=/x", "XDG_RUNTIME_DIR": "/r"}) == "unix:path=/x"


def test_session_address_falls_back_to_the_runtime_dir():
    assert session_address({"XDG_RUNTIME_DIR": "/run/user/1000"}) == "unix:path=/run/user/1000/bus"


def test_no_session_bus_raises():
    with pytest.raises(OSError, match="no session bus"):
        session_address({})


class FakeConnection:
    """Just enough of jeepney's blocking connection: scripted inbound messages, recorded sends."""

    def __init__(self, *messages):
        self.queued = list(messages)
        self.sent: list[int | None] = []
        self.outgoing_serial = itertools.count(1)
        self.closed = False
        self.sock = SimpleNamespace(fileno=lambda: 0)

    def send(self, message, serial=None):
        self.sent.append(serial)

    def receive(self, *, timeout=None):
        if not self.queued:
            raise TimeoutError
        item = self.queued.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def close(self):
        self.closed = True


def _message(body=(), reply_serial=None, message_type=MessageType.method_return, error=None, member="member"):
    fields = {HeaderFields.member: member}
    if reply_serial is not None:
        fields[HeaderFields.reply_serial] = reply_serial
    if error is not None:
        fields[HeaderFields.error_name] = error
    return SimpleNamespace(header=SimpleNamespace(fields=fields, message_type=message_type), body=body)


# A call must never drop a message that arrives before its reply: that message is usually the compositor
# calling us, and losing it loses the edge report entirely.
def test_call_returns_the_reply_and_keeps_messages_that_arrived_first():
    conn = FakeConnection(
        _message(member="Edges", message_type=MessageType.signal),
        _message(body=("ok",), reply_serial=1),
    )
    bus = SessionBus(connection=conn)

    assert bus.call("org.example.Dest", "/org/example", "org.example.Iface", "Member") == ("ok",)
    assert conn.sent == [1]

    kept = bus.receive()
    assert kept is not None and kept.member == "Edges"
    assert bus.receive() is None


def test_a_split_reply_is_matched_by_serial_not_by_arrival_order():
    conn = FakeConnection(
        _message(reply_serial=2),  # a stale reply to an earlier, timed-out call
        _message(body=("mine",), reply_serial=1),
    )
    bus = SessionBus(connection=conn)

    assert bus.call("org.example.Dest", "/org/example", "org.example.Iface", "Member") == ("mine",)
    assert bus.receive().kind == ""


def test_an_error_reply_raises_os_error():
    conn = FakeConnection(_message(reply_serial=1, message_type=MessageType.error, error="org.example.Boom"))
    with pytest.raises(OSError, match="org.example.Boom"):
        SessionBus(connection=conn).call("org.example.Dest", "/org/example", "org.example.Iface", "Member")


def test_a_timeout_raises_os_error():
    with pytest.raises(OSError):
        SessionBus(connection=FakeConnection()).call("org.example.Dest", "/org/example", "org.example.Iface", "Member")


def test_pending_messages_survive_a_timeout():
    conn = FakeConnection(_message(member="State", message_type=MessageType.signal))
    bus = SessionBus(connection=conn)

    with pytest.raises(OSError):
        bus.call("org.example.Dest", "/org/example", "org.example.Iface", "Member")

    assert bus.receive().member == "State"


def test_close_is_idempotent():
    conn = FakeConnection()
    bus = SessionBus(connection=conn)
    bus.close()
    bus.close()
    assert conn.closed
