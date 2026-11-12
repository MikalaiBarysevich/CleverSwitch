import ctypes

WM_INPUT = 0x00FF
WM_QUIT = 0x0012

_SM_XVIRTUALSCREEN = 76
_SM_YVIRTUALSCREEN = 77
_SM_CXVIRTUALSCREEN = 78
_SM_CYVIRTUALSCREEN = 79
_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
_KEY_DOWN = 0x8000
_HWND_MESSAGE = -3
_QS_RAWINPUT = 0x0400
_RIDEV_REMOVE = 0x00000001
_RIDEV_INPUTSINK = 0x00000100
_USAGE_PAGE_GENERIC_DESKTOP = 0x01
_USAGE_MOUSE = 0x02
_USAGE_KEYBOARD = 0x06


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", ctypes.c_ulong),
        ("pt", _POINT),
        ("lPrivate", ctypes.c_ulong),
    ]


class _WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("style", ctypes.c_uint),
        ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", ctypes.c_void_p),
        ("hIcon", ctypes.c_void_p),
        ("hCursor", ctypes.c_void_p),
        ("hbrBackground", ctypes.c_void_p),
        ("lpszMenuName", ctypes.c_wchar_p),
        ("lpszClassName", ctypes.c_wchar_p),
        ("hIconSm", ctypes.c_void_p),
    ]


class _RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [
        ("usUsagePage", ctypes.c_ushort),
        ("usUsage", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("hwndTarget", ctypes.c_void_p),
    ]


class User32:
    def __init__(self) -> None:
        dll = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        p = ctypes.c_void_p

        dll.GetCursorPos.argtypes = [ctypes.POINTER(_POINT)]
        dll.GetCursorPos.restype = ctypes.c_int
        dll.GetAsyncKeyState.argtypes = [ctypes.c_int]
        dll.GetAsyncKeyState.restype = ctypes.c_short
        dll.GetSystemMetrics.argtypes = [ctypes.c_int]
        dll.GetSystemMetrics.restype = ctypes.c_int
        dll.RegisterClassExW.argtypes = [ctypes.POINTER(_WNDCLASSEXW)]
        dll.RegisterClassExW.restype = ctypes.c_ushort
        dll.UnregisterClassW.argtypes = [ctypes.c_wchar_p, p]
        dll.UnregisterClassW.restype = ctypes.c_int
        dll.CreateWindowExW.argtypes = [
            ctypes.c_ulong,
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            ctypes.c_ulong,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            p,
            p,
            p,
            p,
        ]
        dll.CreateWindowExW.restype = p
        dll.DestroyWindow.argtypes = [p]
        dll.DestroyWindow.restype = ctypes.c_int
        dll.RegisterRawInputDevices.argtypes = [ctypes.POINTER(_RAWINPUTDEVICE), ctypes.c_uint, ctypes.c_uint]
        dll.RegisterRawInputDevices.restype = ctypes.c_int
        dll.GetMessageW.argtypes = [ctypes.POINTER(_MSG), p, ctypes.c_uint, ctypes.c_uint]
        dll.GetMessageW.restype = ctypes.c_int
        dll.DispatchMessageW.argtypes = [ctypes.POINTER(_MSG)]
        dll.DispatchMessageW.restype = ctypes.c_ssize_t
        dll.PostThreadMessageW.argtypes = [ctypes.c_ulong, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
        dll.PostThreadMessageW.restype = ctypes.c_int
        dll.GetQueueStatus.argtypes = [ctypes.c_uint]
        dll.GetQueueStatus.restype = ctypes.c_ulong
        kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
        kernel32.GetModuleHandleW.restype = p
        kernel32.GetCurrentThreadId.argtypes = []
        kernel32.GetCurrentThreadId.restype = ctypes.c_ulong

        self._set_dpi_context = getattr(dll, "SetThreadDpiAwarenessContext", None)
        if self._set_dpi_context is not None:
            self._set_dpi_context.argtypes = [p]
            self._set_dpi_context.restype = p
        self._dll = dll
        self._kernel32 = kernel32
        self._msg = _MSG()
        self._class_name = f"CleverSwitchEdgeSink{id(self):x}"
        self._instance = None
        self._hwnd = None

    # Per-thread, so cursor and virtual-screen coordinates share one unscaled space on mixed-DPI setups.
    def use_per_monitor_dpi(self) -> None:
        if self._set_dpi_context is not None:
            self._set_dpi_context(ctypes.c_void_p(_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2))

    def current_thread_id(self) -> int:
        return self._kernel32.GetCurrentThreadId()

    # A message-only window whose procedure is user32's own DefWindowProcW, so no Python callback runs
    # inside the input path. RIDEV_INPUTSINK delivers mouse and keyboard input while it is not focused.
    def open_sink_window(self) -> None:
        self._instance = self._kernel32.GetModuleHandleW(None)
        window_class = _WNDCLASSEXW()
        window_class.cbSize = ctypes.sizeof(_WNDCLASSEXW)
        window_class.lpfnWndProc = ctypes.cast(self._dll.DefWindowProcW, ctypes.c_void_p).value
        window_class.hInstance = self._instance
        window_class.lpszClassName = self._class_name
        if not self._dll.RegisterClassExW(ctypes.byref(window_class)):
            raise ctypes.WinError(ctypes.get_last_error())
        hwnd = self._dll.CreateWindowExW(
            0,
            self._class_name,
            self._class_name,
            0,
            0,
            0,
            0,
            0,
            ctypes.c_void_p(_HWND_MESSAGE),
            None,
            self._instance,
            None,
        )
        if not hwnd:
            error = ctypes.get_last_error()
            self._dll.UnregisterClassW(self._class_name, self._instance)
            raise ctypes.WinError(error)
        self._hwnd = hwnd
        if not self._register_raw_input(_RIDEV_INPUTSINK, hwnd):
            error = ctypes.get_last_error()
            self._dll.DestroyWindow(hwnd)
            self._dll.UnregisterClassW(self._class_name, self._instance)
            self._hwnd = None
            raise ctypes.WinError(error)

    def close_sink_window(self) -> None:
        if self._hwnd is None:
            return
        self._register_raw_input(_RIDEV_REMOVE, None)
        self._dll.DestroyWindow(self._hwnd)
        self._dll.UnregisterClassW(self._class_name, self._instance)
        self._hwnd = None

    # (GetMessageW result, message id): 0 means WM_QUIT, -1 an error.
    def next_message(self) -> tuple[int, int]:
        result = self._dll.GetMessageW(ctypes.byref(self._msg), None, 0, 0)
        return result, self._msg.message

    # DefWindowProcW releases the raw input data of a WM_INPUT.
    def dispatch(self) -> None:
        self._dll.DispatchMessageW(ctypes.byref(self._msg))

    def raw_input_pending(self) -> bool:
        return bool((self._dll.GetQueueStatus(_QS_RAWINPUT) >> 16) & _QS_RAWINPUT)

    def post_quit(self, thread_id: int) -> None:
        self._dll.PostThreadMessageW(thread_id, WM_QUIT, 0, 0)

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

    def _register_raw_input(self, flags: int, hwnd) -> bool:
        devices = (_RAWINPUTDEVICE * 2)(
            _RAWINPUTDEVICE(_USAGE_PAGE_GENERIC_DESKTOP, _USAGE_MOUSE, flags, hwnd),
            _RAWINPUTDEVICE(_USAGE_PAGE_GENERIC_DESKTOP, _USAGE_KEYBOARD, flags, hwnd),
        )
        return bool(self._dll.RegisterRawInputDevices(devices, 2, ctypes.sizeof(_RAWINPUTDEVICE)))
