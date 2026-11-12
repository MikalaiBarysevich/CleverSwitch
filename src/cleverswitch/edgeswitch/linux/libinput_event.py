from __future__ import annotations

import dataclasses

DEVICE_ADDED = 1
DEVICE_REMOVED = 2
KEYBOARD_KEY = 300
POINTER_MOTION = 400
POINTER_MOTION_ABSOLUTE = 401
POINTER_BUTTON = 402


@dataclasses.dataclass(frozen=True)
class LibinputEvent:
    type: int
    device: int = 0  # the device pointer, only used as a key
    keyboard: bool = False
    pointer: bool = False
    name: str = ""
    code: int = 0
    seat_count: int = 0
