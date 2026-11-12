import ctypes

_SM_XVIRTUALSCREEN = 76
_SM_YVIRTUALSCREEN = 77
_SM_CXVIRTUALSCREEN = 78
_SM_CYVIRTUALSCREEN = 79
_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
_KEY_DOWN = 0x8000


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class User32:
    def __init__(self) -> None:
        dll = ctypes.WinDLL("user32")
        dll.GetCursorPos.argtypes = [ctypes.POINTER(_POINT)]
        dll.GetCursorPos.restype = ctypes.c_int
        dll.GetAsyncKeyState.argtypes = [ctypes.c_int]
        dll.GetAsyncKeyState.restype = ctypes.c_short
        dll.GetSystemMetrics.argtypes = [ctypes.c_int]
        dll.GetSystemMetrics.restype = ctypes.c_int
        self._set_dpi_context = getattr(dll, "SetThreadDpiAwarenessContext", None)
        if self._set_dpi_context is not None:
            self._set_dpi_context.argtypes = [ctypes.c_void_p]
            self._set_dpi_context.restype = ctypes.c_void_p
        self._dll = dll

    # Per-thread, so cursor and virtual-screen coordinates share one unscaled space on mixed-DPI setups.
    def use_per_monitor_dpi(self) -> None:
        if self._set_dpi_context is not None:
            self._set_dpi_context(ctypes.c_void_p(_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2))

    # None on the secure desktop (lock screen, UAC prompt).
    def cursor_pos(self) -> tuple[int, int] | None:
        point = _POINT()
        if not self._dll.GetCursorPos(ctypes.byref(point)):
            return None
        return point.x, point.y

    def key_down(self, vk: int) -> bool:
        return bool(self._dll.GetAsyncKeyState(vk) & _KEY_DOWN)

    def virtual_screen(self) -> tuple[int, int, int, int]:
        metrics = self._dll.GetSystemMetrics
        return (
            metrics(_SM_XVIRTUALSCREEN),
            metrics(_SM_YVIRTUALSCREEN),
            metrics(_SM_CXVIRTUALSCREEN),
            metrics(_SM_CYVIRTUALSCREEN),
        )
