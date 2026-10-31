import ctypes
import uuid

CR_SUCCESS = 0
ERROR_SUCCESS = 0

ACTION_INTERFACE_ARRIVAL = 0
ACTION_INTERFACE_REMOVAL = 1

_FILTER_TYPE_DEVICEINTERFACE = 0
_GUID_DEVINTERFACE_HID = "4d1e55b2-f16f-11cf-88cb-001111000030"
# CM_NOTIFY_EVENT_DATA: FilterType, Reserved, then DeviceInterface { GUID ClassGuid; WCHAR SymbolicLink[] }
_SYMBOLIC_LINK_OFFSET = 4 + 4 + 16

# WINFUNCTYPE only exists on Windows; the fallback lets the module import elsewhere.
_FUNCTYPE = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
NotifyCallback = _FUNCTYPE(
    ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32
)


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _FilterUnion(ctypes.Union):
    _fields_ = [("ClassGuid", _GUID), ("hTarget", ctypes.c_void_p), ("InstanceId", ctypes.c_wchar * 200)]


class _NotifyFilter(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint32),
        ("Flags", ctypes.c_uint32),
        ("FilterType", ctypes.c_int),
        ("Reserved", ctypes.c_uint32),
        ("u", _FilterUnion),
    ]


class CfgMgr32:
    def __init__(self) -> None:
        dll = ctypes.WinDLL("cfgmgr32")
        dll.CM_Register_Notification.argtypes = [
            ctypes.POINTER(_NotifyFilter),
            ctypes.c_void_p,
            NotifyCallback,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        dll.CM_Register_Notification.restype = ctypes.c_uint32
        dll.CM_Unregister_Notification.argtypes = [ctypes.c_void_p]
        dll.CM_Unregister_Notification.restype = ctypes.c_uint32
        self._dll = dll

    def register_hid_interfaces(self, callback) -> int:
        notify_filter = _NotifyFilter()
        notify_filter.cbSize = ctypes.sizeof(_NotifyFilter)
        notify_filter.FilterType = _FILTER_TYPE_DEVICEINTERFACE
        ctypes.memmove(ctypes.byref(notify_filter.u.ClassGuid), uuid.UUID(_GUID_DEVINTERFACE_HID).bytes_le, 16)
        handle = ctypes.c_void_p()
        result = self._dll.CM_Register_Notification(ctypes.byref(notify_filter), None, callback, ctypes.byref(handle))
        if result != CR_SUCCESS:
            raise OSError(f"CM_Register_Notification failed: CONFIGRET 0x{result:X}")
        return handle.value

    def unregister(self, handle: int) -> None:
        self._dll.CM_Unregister_Notification(handle)

    def symbolic_link(self, event_data: int) -> str:
        return ctypes.wstring_at(event_data + _SYMBOLIC_LINK_OFFSET)
