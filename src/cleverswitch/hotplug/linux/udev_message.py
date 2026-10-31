import re
import socket
import struct

ACTION_ADD = "add"
ACTION_REMOVE = "remove"

_PREFIX = b"libudev\x00"
_MAGIC = 0xFEEDCAFE
_HEADER = struct.Struct("=III")
_UCRED = struct.Struct("=iII")

_HIDRAW_DEVPATH = re.compile(r"/[0-9A-F]{4}:046D:([0-9A-F]{4})\.[0-9A-F]+/hidraw/hidraw\d+$", re.IGNORECASE)


def parse_udev_message(data: bytes) -> dict[str, str] | None:
    if len(data) < len(_PREFIX) + 4 + _HEADER.size or not data.startswith(_PREFIX):
        return None
    if struct.unpack_from(">I", data, len(_PREFIX))[0] != _MAGIC:
        return None
    _header_size, offset, length = _HEADER.unpack_from(data, len(_PREFIX) + 4)
    properties: dict[str, str] = {}
    for entry in data[offset : offset + length].split(b"\x00"):
        key, sep, value = entry.partition(b"=")
        if sep:
            properties[key.decode(errors="replace")] = value.decode(errors="replace")
    return properties


def hidraw_pid(devpath: str) -> int | None:
    match = _HIDRAW_DEVPATH.search(devpath)
    return int(match.group(1), 16) if match else None


def hidraw_event(data: bytes) -> tuple[str, int] | None:
    properties = parse_udev_message(data)
    if properties is None or properties.get("SUBSYSTEM") != "hidraw":
        return None
    action = properties.get("ACTION")
    if action not in (ACTION_ADD, ACTION_REMOVE):
        return None
    pid = hidraw_pid(properties.get("DEVPATH", ""))
    return None if pid is None else (action, pid)


def sender_uid(ancdata: list[tuple[int, int, bytes]]) -> int | None:
    for level, kind, payload in ancdata:
        if level == socket.SOL_SOCKET and kind == getattr(socket, "SCM_CREDENTIALS", None):
            if len(payload) >= _UCRED.size:
                return _UCRED.unpack_from(payload)[1]
    return None
