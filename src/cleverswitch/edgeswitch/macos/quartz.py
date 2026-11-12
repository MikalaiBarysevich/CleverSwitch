import ctypes
from collections.abc import Callable

_CORE_FOUNDATION = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
_CORE_GRAPHICS = "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"

_HID_SYSTEM_STATE = 1  # kCGEventSourceStateHIDSystemState: the physical keys and buttons
_MAX_DISPLAYS = 32
_SESSION_EVENT_TAP = 1  # kCGSessionEventTap
_HEAD_INSERT = 0  # kCGHeadInsertEventTap
_LISTEN_ONLY = 1  # kCGEventTapOptionListenOnly
_RUN_FOREVER_S = 1e10

TAP_DISABLED_BY_TIMEOUT = 0xFFFFFFFE
TAP_DISABLED_BY_USER_INPUT = 0xFFFFFFFF
MOUSE_MOVED = 5
LEFT_MOUSE_DRAGGED = 6
RIGHT_MOUSE_DRAGGED = 7
OTHER_MOUSE_DRAGGED = 27
# Button down/up 1-4 and 25-26, moved and dragged 5-7 and 27, flagsChanged 12.
_EVENT_MASK = sum(1 << t for t in (1, 2, 3, 4, 5, 6, 7, 12, 25, 26, 27))

TapCallback = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p)
_PerformCallback = ctypes.CFUNCTYPE(None, ctypes.c_void_p)


class _CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class _CGSize(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]


class _CGRect(ctypes.Structure):
    _fields_ = [("origin", _CGPoint), ("size", _CGSize)]


class _RunLoopSourceContext(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_long),
        ("info", ctypes.c_void_p),
        ("retain", ctypes.c_void_p),
        ("release", ctypes.c_void_p),
        ("copyDescription", ctypes.c_void_p),
        ("equal", ctypes.c_void_p),
        ("hash", ctypes.c_void_p),
        ("schedule", ctypes.c_void_p),
        ("cancel", ctypes.c_void_p),
        ("perform", _PerformCallback),
    ]


class Quartz:
    """A listen-only session event tap on the calling thread's run loop. A second, version-0 run loop source
    stops the loop: unlike a bare CFRunLoopStop, a signal sent before the loop runs is not lost."""

    def __init__(self) -> None:
        cf = ctypes.CDLL(_CORE_FOUNDATION)
        cg = ctypes.CDLL(_CORE_GRAPHICS)
        p = ctypes.c_void_p

        cf.CFRelease.argtypes = [p]
        cf.CFRelease.restype = None
        cf.CFMachPortCreateRunLoopSource.argtypes = [p, p, ctypes.c_long]
        cf.CFMachPortCreateRunLoopSource.restype = p
        cf.CFMachPortInvalidate.argtypes = [p]
        cf.CFMachPortInvalidate.restype = None
        cf.CFRunLoopGetCurrent.argtypes = []
        cf.CFRunLoopGetCurrent.restype = p
        cf.CFRunLoopAddSource.argtypes = [p, p, p]
        cf.CFRunLoopAddSource.restype = None
        cf.CFRunLoopRemoveSource.argtypes = [p, p, p]
        cf.CFRunLoopRemoveSource.restype = None
        cf.CFRunLoopSourceCreate.argtypes = [p, ctypes.c_long, ctypes.POINTER(_RunLoopSourceContext)]
        cf.CFRunLoopSourceCreate.restype = p
        cf.CFRunLoopSourceSignal.argtypes = [p]
        cf.CFRunLoopSourceSignal.restype = None
        cf.CFRunLoopSourceInvalidate.argtypes = [p]
        cf.CFRunLoopSourceInvalidate.restype = None
        cf.CFRunLoopWakeUp.argtypes = [p]
        cf.CFRunLoopWakeUp.restype = None
        cf.CFRunLoopRunInMode.argtypes = [p, ctypes.c_double, ctypes.c_bool]
        cf.CFRunLoopRunInMode.restype = ctypes.c_int32
        cf.CFRunLoopStop.argtypes = [p]
        cf.CFRunLoopStop.restype = None
        cg.CGEventTapCreate.argtypes = [
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_uint64,
            TapCallback,
            p,
        ]
        cg.CGEventTapCreate.restype = p
        cg.CGEventTapEnable.argtypes = [p, ctypes.c_bool]
        cg.CGEventTapEnable.restype = None
        cg.CGEventTapIsEnabled.argtypes = [p]
        cg.CGEventTapIsEnabled.restype = ctypes.c_bool
        cg.CGEventGetFlags.argtypes = [p]
        cg.CGEventGetFlags.restype = ctypes.c_uint64
        cg.CGEventGetLocation.argtypes = [p]
        cg.CGEventGetLocation.restype = _CGPoint
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
        self._preflight = getattr(cg, "CGPreflightListenEventAccess", None)
        if self._preflight is not None:
            self._preflight.argtypes = []
            self._preflight.restype = ctypes.c_bool

        self._cf = cf
        self._cg = cg
        self._default_mode = ctypes.c_void_p.in_dll(cf, "kCFRunLoopDefaultMode")
        self._common_modes = ctypes.c_void_p.in_dll(cf, "kCFRunLoopCommonModes")
        self._tap = None
        self._tap_source = None
        self._stop_source = None
        self._run_loop = None
        self._callback = None
        self._perform = None
        self._context = None

    # True where the check does not exist (before macOS 10.15).
    def listen_access_granted(self) -> bool:
        return True if self._preflight is None else bool(self._preflight())

    def open_tap(self, handler: Callable[[int, int], None]) -> None:
        def on_event(_proxy, event_type, event, _info):
            handler(event_type, event)
            return event

        self._callback = TapCallback(on_event)
        tap = self._cg.CGEventTapCreate(
            _SESSION_EVENT_TAP, _HEAD_INSERT, _LISTEN_ONLY, _EVENT_MASK, self._callback, None
        )
        if not tap:
            raise PermissionError("cannot create an event tap")
        self._tap = tap
        self._run_loop = self._cf.CFRunLoopGetCurrent()
        self._tap_source = self._cf.CFMachPortCreateRunLoopSource(None, tap, 0)
        self._perform = _PerformCallback(lambda _info: self._cf.CFRunLoopStop(self._cf.CFRunLoopGetCurrent()))
        self._context = _RunLoopSourceContext(version=0, perform=self._perform)
        self._stop_source = self._cf.CFRunLoopSourceCreate(None, 0, ctypes.byref(self._context))
        if not self._tap_source or not self._stop_source:
            self.close_tap()
            raise OSError("cannot create run loop sources for the event tap")
        self._cf.CFRunLoopAddSource(self._run_loop, self._tap_source, self._common_modes)
        self._cf.CFRunLoopAddSource(self._run_loop, self._stop_source, self._common_modes)
        self._cg.CGEventTapEnable(tap, True)

    def run(self) -> None:
        self._cf.CFRunLoopRunInMode(self._default_mode, _RUN_FOREVER_S, False)

    # Any thread.
    def wake_stop(self) -> None:
        self._cf.CFRunLoopSourceSignal(self._stop_source)
        self._cf.CFRunLoopWakeUp(self._run_loop)

    # From the tap callback, on the run loop's own thread.
    def stop_run(self) -> None:
        self._cf.CFRunLoopStop(self._cf.CFRunLoopGetCurrent())

    def reenable_tap(self) -> bool:
        self._cg.CGEventTapEnable(self._tap, True)
        return bool(self._cg.CGEventTapIsEnabled(self._tap))

    def event_flags(self, event: int) -> int:
        return self._cg.CGEventGetFlags(event)

    # Global display coordinates: origin at the main display's top-left, y grows down.
    def event_location(self, event: int) -> tuple[float, float]:
        point = self._cg.CGEventGetLocation(event)
        return point.x, point.y

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

    def close_tap(self) -> None:
        if self._tap is not None:
            self._cg.CGEventTapEnable(self._tap, False)
        for source in (self._tap_source, self._stop_source):
            if source:
                self._cf.CFRunLoopRemoveSource(self._run_loop, source, self._common_modes)
        if self._stop_source:
            self._cf.CFRunLoopSourceInvalidate(self._stop_source)
            self._cf.CFRelease(self._stop_source)
        if self._tap_source:
            self._cf.CFRelease(self._tap_source)
        if self._tap is not None:
            self._cf.CFMachPortInvalidate(self._tap)
            self._cf.CFRelease(self._tap)
        self._tap = self._tap_source = self._stop_source = None
