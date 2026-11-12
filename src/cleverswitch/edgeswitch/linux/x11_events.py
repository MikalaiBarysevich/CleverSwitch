from __future__ import annotations

import dataclasses
import struct

GENERIC_EVENT = 35
CONFIGURE_NOTIFY = 22
MAPPING_NOTIFY = 34
XI_RAW_KEY_PRESS = 13
XI_RAW_KEY_RELEASE = 14
XI_RAW_BUTTON_PRESS = 15
XI_RAW_BUTTON_RELEASE = 16
XI_RAW_MOTION = 17
MAPPING_MODIFIER = 0
MAPPING_KEYBOARD = 1


@dataclasses.dataclass(frozen=True)
class RawEvent:
    event_type: int
    detail: int


@dataclasses.dataclass(frozen=True)
class ConfigureEvent:
    window: int
    x: int
    y: int
    width: int
    height: int


@dataclasses.dataclass(frozen=True)
class MappingEvent:
    request: int


def decode(event: bytes, xinput_opcode: int) -> RawEvent | ConfigureEvent | MappingEvent | None:
    kind = event[0] & 0x7F  # the high bit marks a SendEvent
    if kind == GENERIC_EVENT and event[1] == xinput_opcode:
        (event_type,) = struct.unpack_from("=H", event, 8)
        (detail,) = struct.unpack_from("=I", event, 16)  # after deviceid (10) and time (12)
        return RawEvent(event_type, detail)
    if kind == CONFIGURE_NOTIFY:
        (window,) = struct.unpack_from("=I", event, 8)
        x, y, width, height = struct.unpack_from("=hhHH", event, 16)
        return ConfigureEvent(window, x, y, width, height)
    if kind == MAPPING_NOTIFY:
        return MappingEvent(event[4])
    return None
