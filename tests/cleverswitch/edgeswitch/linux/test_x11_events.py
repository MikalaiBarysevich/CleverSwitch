import struct

import pytest

from cleverswitch.edgeswitch.linux import x11_events
from cleverswitch.edgeswitch.linux.x11_events import ConfigureEvent, MappingEvent, RawEvent, decode

OPCODE = 131


def generic(event_type, detail, opcode=OPCODE, sent=False):
    head = (x11_events.GENERIC_EVENT | (0x80 if sent else 0), opcode)
    return struct.pack("=BBHIHHII", *head, 0, 0, event_type, 0, 0xDEADBEEF, detail).ljust(32, b"\0")


def configure(window, x, y, width, height):
    event = bytearray(32)
    event[0] = x11_events.CONFIGURE_NOTIFY
    struct.pack_into("=I", event, 8, window)
    struct.pack_into("=hhHH", event, 16, x, y, width, height)
    return bytes(event)


def mapping(request):
    event = bytearray(32)
    event[0] = x11_events.MAPPING_NOTIFY
    event[4] = request
    return bytes(event)


def test_decodes_a_raw_key_press():
    assert decode(generic(x11_events.XI_RAW_KEY_PRESS, 37), OPCODE) == RawEvent(x11_events.XI_RAW_KEY_PRESS, 37)


def test_send_event_bit_is_ignored():
    assert decode(generic(x11_events.XI_RAW_MOTION, 0, sent=True), OPCODE) == RawEvent(x11_events.XI_RAW_MOTION, 0)


def test_generic_event_of_another_extension_is_ignored():
    assert decode(generic(x11_events.XI_RAW_MOTION, 0, opcode=OPCODE + 1), OPCODE) is None


def test_decodes_configure_notify():
    assert decode(configure(0x1EE, -5, 7, 3840, 1080), OPCODE) == ConfigureEvent(0x1EE, -5, 7, 3840, 1080)


def test_decodes_mapping_notify():
    assert decode(mapping(x11_events.MAPPING_KEYBOARD), OPCODE) == MappingEvent(x11_events.MAPPING_KEYBOARD)


@pytest.mark.parametrize("kind", [2, 6, 12])  # KeyPress, MotionNotify, Expose
def test_other_events_are_ignored(kind):
    assert decode(bytes([kind]).ljust(32, b"\0"), OPCODE) is None
