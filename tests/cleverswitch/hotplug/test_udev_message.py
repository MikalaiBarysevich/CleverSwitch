"""Unit tests for hotplug/linux/udev_message.py."""

from __future__ import annotations

import socket
import struct

import pytest

from cleverswitch.hotplug.linux.udev_message import (
    ACTION_ADD,
    ACTION_REMOVE,
    hidraw_event,
    hidraw_pid,
    parse_udev_message,
    sender_uid,
)

BT_KEYBOARD = "/devices/virtual/misc/uhid/0005:046D:B35B.0038/hidraw/hidraw8"
RECEIVER = "/devices/pci0000:00/0000:00:01.3/0000:02:00.0/usb1/1-6/1-6:1.2/0003:046D:C52B.002F/hidraw/hidraw5"
RECEIVER_CHILD = RECEIVER.replace("/hidraw/hidraw5", "/0003:046D:408A.0030/hidraw/hidraw4")
OTHER_VENDOR = "/devices/pci0000:00/0000:00:08.1/0000:09:00.3/usb3/3-3/3-3:1.0/0003:5653:0001.0020/hidraw/hidraw0"


def _udev_message(magic=0xFEEDCAFE, prefix=b"libudev\x00", **properties):
    body = b"".join(f"{key}={value}".encode() + b"\x00" for key, value in properties.items())
    header = prefix + struct.pack(">I", magic) + struct.pack("=IIIIIII", 40, 40, len(body), 0, 0, 0, 0)
    return header + body


def _hidraw(action, devpath, subsystem="hidraw"):
    return _udev_message(ACTION=action, DEVPATH=devpath, SUBSYSTEM=subsystem, DEVNAME="/dev/hidraw8", SEQNUM="4242")


def test_parses_properties():
    properties = parse_udev_message(_hidraw("add", BT_KEYBOARD))
    assert properties["ACTION"] == "add"
    assert properties["DEVPATH"] == BT_KEYBOARD
    assert properties["SUBSYSTEM"] == "hidraw"
    assert properties["SEQNUM"] == "4242"


@pytest.mark.parametrize(
    "data",
    [
        b"add@/devices/virtual/misc/uhid\x00ACTION=add\x00",
        _udev_message(prefix=b"systemd\x00", ACTION="add"),
        _udev_message(magic=0xDEADBEEF, ACTION="add"),
        b"libudev\x00\xfe\xed",
    ],
)
def test_rejects_anything_but_a_udev_message(data):
    assert parse_udev_message(data) is None


@pytest.mark.parametrize(
    ("devpath", "pid"),
    [(BT_KEYBOARD, 0xB35B), (RECEIVER, 0xC52B), (RECEIVER_CHILD, 0x408A), (OTHER_VENDOR, None), ("/devices/x", None)],
)
def test_hidraw_pid_is_the_device_right_above_the_node(devpath, pid):
    assert hidraw_pid(devpath) == pid


def test_hidraw_pid_is_case_insensitive():
    assert hidraw_pid("/devices/0005:046d:b35b.0038/hidraw/hidraw8") == 0xB35B


@pytest.mark.parametrize(("action", "expected"), [("add", ACTION_ADD), ("remove", ACTION_REMOVE)])
def test_hidraw_event_for_logitech_add_and_remove(action, expected):
    assert hidraw_event(_hidraw(action, BT_KEYBOARD)) == (expected, 0xB35B)


@pytest.mark.parametrize(
    "data",
    [
        _hidraw("change", BT_KEYBOARD),
        _hidraw("bind", BT_KEYBOARD),
        _hidraw("add", BT_KEYBOARD, subsystem="input"),
        _hidraw("add", OTHER_VENDOR),
        _udev_message(ACTION="add", SUBSYSTEM="hidraw"),
        b"garbage",
    ],
)
def test_hidraw_event_ignores_everything_else(data):
    assert hidraw_event(data) is None


def _credentials(uid):
    return (socket.SOL_SOCKET, socket.SCM_CREDENTIALS, struct.pack("=iII", 321, uid, uid))


def test_sender_uid_reads_the_credentials():
    assert sender_uid([_credentials(0)]) == 0
    assert sender_uid([_credentials(1000)]) == 1000


def test_sender_uid_without_credentials_is_none():
    assert sender_uid([]) is None
    assert sender_uid([(socket.SOL_SOCKET, socket.SCM_CREDENTIALS, b"\x00")]) is None
    assert sender_uid([(socket.SOL_SOCKET + 1, socket.SCM_CREDENTIALS, struct.pack("=iII", 1, 0, 0))]) is None
