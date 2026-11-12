import ctypes

_CORE_FOUNDATION = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
_CORE_GRAPHICS = "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"

_HID_SYSTEM_STATE = 1  # kCGEventSourceStateHIDSystemState: the physical keys and buttons
_MAX_DISPLAYS = 32


class _CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class _CGSize(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]


class _CGRect(ctypes.Structure):
    _fields_ = [("origin", _CGPoint), ("size", _CGSize)]


class Quartz:
    def __init__(self) -> None:
        cf = ctypes.CDLL(_CORE_FOUNDATION)
        cg = ctypes.CDLL(_CORE_GRAPHICS)
        p = ctypes.c_void_p

        cf.CFRelease.argtypes = [p]
        cf.CFRelease.restype = None
        cg.CGEventCreate.argtypes = [p]
        cg.CGEventCreate.restype = p
        cg.CGEventGetLocation.argtypes = [p]
        cg.CGEventGetLocation.restype = _CGPoint
        cg.CGEventSourceFlagsState.argtypes = [ctypes.c_int32]
        cg.CGEventSourceFlagsState.restype = ctypes.c_uint64
        cg.CGEventSourceButtonState.argtypes = [ctypes.c_int32, ctypes.c_uint32]
        cg.CGEventSourceButtonState.restype = ctypes.c_bool
        cg.CGGetActiveDisplayList.argtypes = [
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_uint32),
        ]
        cg.CGGetActiveDisplayList.restype = ctypes.c_int32
        cg.CGDisplayBounds.argtypes = [ctypes.c_uint32]
        cg.CGDisplayBounds.restype = _CGRect

        self._cf = cf
        self._cg = cg

    # Global display coordinates: origin at the main display's top-left, y grows down.
    # None without a window server session.
    def cursor_pos(self) -> tuple[float, float] | None:
        event = self._cg.CGEventCreate(None)
        if not event:
            return None
        try:
            point = self._cg.CGEventGetLocation(event)
            return point.x, point.y
        finally:
            self._cf.CFRelease(event)

    def flags(self) -> int:
        return self._cg.CGEventSourceFlagsState(_HID_SYSTEM_STATE)

    def button_down(self, button: int) -> bool:
        return bool(self._cg.CGEventSourceButtonState(_HID_SYSTEM_STATE, button))

    def display_bounds(self) -> list[tuple[float, float, float, float]]:
        displays = (ctypes.c_uint32 * _MAX_DISPLAYS)()
        count = ctypes.c_uint32(0)
        if self._cg.CGGetActiveDisplayList(_MAX_DISPLAYS, displays, ctypes.byref(count)) != 0:
            return []
        result = []
        for display in displays[: count.value]:
            rect = self._cg.CGDisplayBounds(display)
            result.append((rect.origin.x, rect.origin.y, rect.size.width, rect.size.height))
        return result
