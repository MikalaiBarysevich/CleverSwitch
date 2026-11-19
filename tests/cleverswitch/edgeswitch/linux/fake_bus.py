import os
from collections import deque

from cleverswitch.edgeswitch.linux.edge_bus import (
    CALL,
    DBUS,
    INTERFACE,
    OBJECT_PATH,
    SIGNAL,
    BusMessage,
)

PEER_OWNER = ":1.7"


class FakeBus:
    """A session bus with scripted call results and a queue of inbound messages. Its fd is a real pipe that
    is readable while messages are queued, so poll() works."""

    def __init__(self, owners=None, request_name=1, results=None):
        self.owners = dict(owners or {})
        self.request_name = request_name
        self.results = dict(results or {})
        self.calls = []
        self.replies = []
        self.errors = []
        self.inbound = deque()
        self.closed = False
        self._r, self._w = os.pipe()
        os.set_blocking(self._r, False)

    def fd(self):
        return self._r

    def call(self, destination, path, interface, member, signature="", body=()):
        self.calls.append((destination, path, interface, member, tuple(body)))
        key = (destination, member)
        if key in self.results:
            result = self.results[key]
            if isinstance(result, BaseException):
                raise result
            return result(*body) if callable(result) else result
        if destination == DBUS:
            if member == "NameHasOwner":
                return (body[0] in self.owners,)
            if member == "GetNameOwner":
                if body[0] not in self.owners:
                    raise OSError("NameHasNoOwner")
                return (self.owners[body[0]],)
            if member == "RequestName":
                return (self.request_name,)
            if member == "AddMatch":
                return ()
        return ()

    def push(self, *messages):
        self.inbound.extend(messages)
        os.write(self._w, b"x")

    def receive(self):
        if self.inbound:
            return self.inbound.popleft()
        try:
            os.read(self._r, 64)
        except BlockingIOError:
            pass
        return None

    def reply(self, message):
        self.replies.append(message.member)

    def error(self, message, name):
        self.errors.append((message.member, name))

    def close(self):
        if not self.closed:
            self.closed = True
            os.close(self._r)
            os.close(self._w)

    def member_calls(self, member):
        return [c for c in self.calls if c[3] == member]


def call(member, *body, sender=PEER_OWNER, path=OBJECT_PATH, interface=INTERFACE):
    return BusMessage(CALL, sender=sender, path=path, interface=interface, member=member, body=tuple(body))


def signal(member, *body, sender="", interface="", path=""):
    return BusMessage(SIGNAL, sender=sender, path=path, interface=interface, member=member, body=tuple(body))


def owner_changed(name, new):
    return signal("NameOwnerChanged", name, PEER_OWNER, new, sender=DBUS, interface=DBUS)
