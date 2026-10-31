import ctypes

_CORE_FOUNDATION = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
_IOKIT = "/System/Library/Frameworks/IOKit.framework/IOKit"

_UTF8 = 0x08000100
_SINT32 = 3

DeviceCallback = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p)


class IOKit:
    def __init__(self) -> None:
        cf = ctypes.CDLL(_CORE_FOUNDATION)
        iokit = ctypes.CDLL(_IOKIT)
        p = ctypes.c_void_p

        cf.CFStringCreateWithCString.argtypes = [p, ctypes.c_char_p, ctypes.c_uint32]
        cf.CFStringCreateWithCString.restype = p
        cf.CFNumberCreate.argtypes = [p, ctypes.c_int, p]
        cf.CFNumberCreate.restype = p
        cf.CFNumberGetValue.argtypes = [p, ctypes.c_int, p]
        cf.CFNumberGetValue.restype = ctypes.c_bool
        cf.CFNumberGetTypeID.argtypes = []
        cf.CFNumberGetTypeID.restype = ctypes.c_ulong
        cf.CFGetTypeID.argtypes = [p]
        cf.CFGetTypeID.restype = ctypes.c_ulong
        cf.CFDictionaryCreateMutable.argtypes = [p, ctypes.c_long, p, p]
        cf.CFDictionaryCreateMutable.restype = p
        cf.CFDictionarySetValue.argtypes = [p, p, p]
        cf.CFDictionarySetValue.restype = None
        cf.CFRelease.argtypes = [p]
        cf.CFRelease.restype = None
        cf.CFRunLoopGetCurrent.argtypes = []
        cf.CFRunLoopGetCurrent.restype = p
        cf.CFRunLoopRunInMode.argtypes = [p, ctypes.c_double, ctypes.c_bool]
        cf.CFRunLoopRunInMode.restype = ctypes.c_int32
        cf.CFRunLoopStop.argtypes = [p]
        cf.CFRunLoopStop.restype = None
        cf.CFRunLoopWakeUp.argtypes = [p]
        cf.CFRunLoopWakeUp.restype = None

        iokit.IOHIDManagerCreate.argtypes = [p, ctypes.c_uint32]
        iokit.IOHIDManagerCreate.restype = p
        iokit.IOHIDManagerSetDeviceMatching.argtypes = [p, p]
        iokit.IOHIDManagerSetDeviceMatching.restype = None
        iokit.IOHIDManagerRegisterDeviceMatchingCallback.argtypes = [p, DeviceCallback, p]
        iokit.IOHIDManagerRegisterDeviceMatchingCallback.restype = None
        iokit.IOHIDManagerRegisterDeviceRemovalCallback.argtypes = [p, DeviceCallback, p]
        iokit.IOHIDManagerRegisterDeviceRemovalCallback.restype = None
        iokit.IOHIDManagerScheduleWithRunLoop.argtypes = [p, p, p]
        iokit.IOHIDManagerScheduleWithRunLoop.restype = None
        iokit.IOHIDManagerUnscheduleFromRunLoop.argtypes = [p, p, p]
        iokit.IOHIDManagerUnscheduleFromRunLoop.restype = None
        iokit.IOHIDDeviceGetProperty.argtypes = [p, p]
        iokit.IOHIDDeviceGetProperty.restype = p

        self._cf = cf
        self._iokit = iokit
        self._default_mode = ctypes.c_void_p.in_dll(cf, "kCFRunLoopDefaultMode")
        self._key_callbacks = ctypes.addressof(ctypes.c_byte.in_dll(cf, "kCFTypeDictionaryKeyCallBacks"))
        self._value_callbacks = ctypes.addressof(ctypes.c_byte.in_dll(cf, "kCFTypeDictionaryValueCallBacks"))
        self._number_type_id = cf.CFNumberGetTypeID()
        self._product_id_key = self._string("ProductID")

    def _string(self, text: str) -> int:
        return self._cf.CFStringCreateWithCString(None, text.encode(), _UTF8)

    def _number(self, value: int) -> int:
        number = ctypes.c_int32(value)
        return self._cf.CFNumberCreate(None, _SINT32, ctypes.byref(number))

    def create_manager(self, vendor_id: int, on_match: DeviceCallback, on_remove: DeviceCallback) -> int:
        manager = self._iokit.IOHIDManagerCreate(None, 0)
        if not manager:
            raise OSError("IOHIDManagerCreate failed")
        matching = self._cf.CFDictionaryCreateMutable(None, 0, self._key_callbacks, self._value_callbacks)
        key = self._string("VendorID")
        value = self._number(vendor_id)
        self._cf.CFDictionarySetValue(matching, key, value)
        self._iokit.IOHIDManagerSetDeviceMatching(manager, matching)
        for ref in (key, value, matching):
            self._cf.CFRelease(ref)
        self._iokit.IOHIDManagerRegisterDeviceMatchingCallback(manager, on_match, None)
        self._iokit.IOHIDManagerRegisterDeviceRemovalCallback(manager, on_remove, None)
        self._iokit.IOHIDManagerScheduleWithRunLoop(manager, self._cf.CFRunLoopGetCurrent(), self._default_mode)
        return manager

    def release_manager(self, manager: int) -> None:
        self._iokit.IOHIDManagerUnscheduleFromRunLoop(manager, self._cf.CFRunLoopGetCurrent(), self._default_mode)
        self._cf.CFRelease(manager)

    def current_run_loop(self) -> int:
        return self._cf.CFRunLoopGetCurrent()

    def run(self, seconds: float) -> None:
        self._cf.CFRunLoopRunInMode(self._default_mode, seconds, False)

    def stop(self, run_loop: int) -> None:
        self._cf.CFRunLoopStop(run_loop)
        self._cf.CFRunLoopWakeUp(run_loop)

    def product_id(self, device: int) -> int | None:
        ref = self._iokit.IOHIDDeviceGetProperty(device, self._product_id_key)
        if not ref or self._cf.CFGetTypeID(ref) != self._number_type_id:
            return None
        value = ctypes.c_int32()
        self._cf.CFNumberGetValue(ref, _SINT32, ctypes.byref(value))
        return value.value
