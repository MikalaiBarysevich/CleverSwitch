"""Unit tests for hotplug/linux/netlink_backend.py. The socket is replaced by a fake that fails once."""

from __future__ import annotations

import errno
import os
from unittest.mock import MagicMock

from cleverswitch.event.hid_node_added_event import HidNodeAddedEvent
from cleverswitch.event.hotplug_resync_event import HotplugResyncEvent
from cleverswitch.hotplug.linux import netlink_backend
from cleverswitch.hotplug.linux.netlink_backend import NetlinkHotplugBackend


def _backend():
    topics = MagicMock()
    backend = NetlinkHotplugBackend(topics)
    wake_r, wake_w = os.pipe()
    backend._wake_read, backend._wake_write = wake_r, wake_w
    return backend, topics


def test_socket_error_publishes_a_resync_and_keeps_listening(monkeypatch):
    backend, topics = _backend()
    sock_r, sock_w = os.pipe()
    os.write(sock_w, b"x")
    sock = MagicMock()
    sock.fileno.return_value = sock_r

    def fail_once(*_args):
        os.write(backend._wake_write, b"\0")
        raise OSError(errno.EIO, "socket broke")

    sock.recvmsg.side_effect = fail_once
    backend._sock = sock
    sleep = MagicMock()
    monkeypatch.setattr(netlink_backend.time, "sleep", sleep)

    backend._run()

    sock.recvmsg.assert_called_once()
    topics.hotplug.publish.assert_called_once_with(HotplugResyncEvent(slot=0, pid=0))
    sleep.assert_called_once_with(0.5)


def test_events_after_a_socket_error_are_still_published(monkeypatch):
    backend, topics = _backend()
    sock_r, sock_w = os.pipe()
    os.write(sock_w, b"x")
    sock = MagicMock()
    sock.fileno.return_value = sock_r
    message = b"ACTION=add\0DEVNAME=/dev/hidraw3\0HID_ID=0003:0000046D:0000C52B\0"

    def recv(*_args):
        if sock.recvmsg.call_count == 1:
            raise OSError(errno.EIO, "socket broke")
        os.write(backend._wake_write, b"\0")
        return (message, [], 0, None)

    sock.recvmsg.side_effect = recv
    backend._sock = sock
    monkeypatch.setattr(netlink_backend.time, "sleep", MagicMock())
    monkeypatch.setattr(netlink_backend, "sender_uid", lambda _ancdata: 0)
    monkeypatch.setattr(netlink_backend, "hidraw_event", lambda _data: (netlink_backend.ACTION_ADD, 0x1234))

    backend._run()

    assert topics.hotplug.publish.call_args_list == [
        ((HotplugResyncEvent(slot=0, pid=0),),),
        ((HidNodeAddedEvent(slot=0, pid=0x1234),),),
    ]


def test_hotplug_stops_after_five_consecutive_socket_errors(monkeypatch):
    backend, topics = _backend()
    sock_r, sock_w = os.pipe()
    os.write(sock_w, b"x")
    sock = MagicMock()
    sock.fileno.return_value = sock_r
    sock.recvmsg.side_effect = OSError(errno.EIO, "socket broke")
    backend._sock = sock
    sleep = MagicMock()
    monkeypatch.setattr(netlink_backend.time, "sleep", sleep)

    backend._run()

    assert sock.recvmsg.call_count == 5
    assert topics.hotplug.publish.call_count == 4
    assert sleep.call_count == 4


def test_the_error_budget_resets_after_a_message(monkeypatch):
    backend, topics = _backend()
    sock_r, sock_w = os.pipe()
    os.write(sock_w, b"x")
    sock = MagicMock()
    sock.fileno.return_value = sock_r
    calls = {"n": 0}

    def recv(*_args):
        calls["n"] += 1
        if calls["n"] == 5:
            return (b"ACTION=add\0", [], 0, None)
        if calls["n"] > 9:
            os.write(backend._wake_write, b"\0")
        raise OSError(errno.EIO, "socket broke")

    sock.recvmsg.side_effect = recv
    backend._sock = sock
    monkeypatch.setattr(netlink_backend.time, "sleep", MagicMock())
    monkeypatch.setattr(netlink_backend, "sender_uid", lambda _ancdata: 1)

    backend._run()

    assert calls["n"] == 10
    assert topics.hotplug.publish.call_count == 8
