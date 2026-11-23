import ctypes
from collections.abc import Callable

from .libinput_event import DEVICE_ADDED, DEVICE_REMOVED, KEYBOARD_KEY, POINTER_BUTTON, LibinputEvent

_CAP_KEYBOARD = 0
_CAP_POINTER = 1

_OpenFn = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p)
_CloseFn = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_void_p)


class _Interface(ctypes.Structure):
    _fields_ = [("open_restricted", _OpenFn), ("close_restricted", _CloseFn)]


class Libinput:
    """One libinput context on a seat. libinput finds the devices and follows hotplug through its own udev
    monitor, and opens each through open_restricted, so it reads exactly what this process may read.
    libinput keeps a pointer to the interface, so the callbacks stay referenced for the object's life."""

    def __init__(
        self,
        seat: str,
        open_restricted: Callable[[bytes, int], int],
        close_restricted: Callable[[int], None],
    ) -> None:
        li = ctypes.CDLL("libinput.so.10")
        udev = ctypes.CDLL("libudev.so.1")
        p = ctypes.c_void_p
        udev.udev_new.restype = p
        udev.udev_unref.argtypes = [p]
        udev.udev_unref.restype = p
        li.libinput_udev_create_context.argtypes = [ctypes.POINTER(_Interface), p, p]
        li.libinput_udev_create_context.restype = p
        li.libinput_udev_assign_seat.argtypes = [p, ctypes.c_char_p]
        li.libinput_udev_assign_seat.restype = ctypes.c_int
        li.libinput_unref.argtypes = [p]
        li.libinput_unref.restype = p
        li.libinput_get_fd.argtypes = [p]
        li.libinput_get_fd.restype = ctypes.c_int
        li.libinput_dispatch.argtypes = [p]
        li.libinput_dispatch.restype = ctypes.c_int
        li.libinput_get_event.argtypes = [p]
        li.libinput_get_event.restype = p
        li.libinput_event_destroy.argtypes = [p]
        li.libinput_event_destroy.restype = None
        li.libinput_event_get_type.argtypes = [p]
        li.libinput_event_get_type.restype = ctypes.c_int
        li.libinput_event_get_device.argtypes = [p]
        li.libinput_event_get_device.restype = p
        li.libinput_device_get_name.argtypes = [p]
        li.libinput_device_get_name.restype = ctypes.c_char_p
        li.libinput_device_has_capability.argtypes = [p, ctypes.c_int]
        li.libinput_device_has_capability.restype = ctypes.c_int
        li.libinput_event_get_keyboard_event.argtypes = [p]
        li.libinput_event_get_keyboard_event.restype = p
        li.libinput_event_keyboard_get_key.argtypes = [p]
        li.libinput_event_keyboard_get_key.restype = ctypes.c_uint32
        li.libinput_event_keyboard_get_seat_key_count.argtypes = [p]
        li.libinput_event_keyboard_get_seat_key_count.restype = ctypes.c_uint32
        li.libinput_event_get_pointer_event.argtypes = [p]
        li.libinput_event_get_pointer_event.restype = p
        li.libinput_event_pointer_get_button.argtypes = [p]
        li.libinput_event_pointer_get_button.restype = ctypes.c_uint32
        li.libinput_event_pointer_get_seat_button_count.argtypes = [p]
        li.libinput_event_pointer_get_seat_button_count.restype = ctypes.c_uint32
        self._li = li

        self._open_cb = _OpenFn(lambda path, flags, _data: open_restricted(path, flags))
        self._close_cb = _CloseFn(lambda fd, _data: close_restricted(fd))
        self._iface = _Interface(self._open_cb, self._close_cb)

        handle = udev.udev_new()
        if not handle:
            raise OSError("udev_new failed")
        ctx = li.libinput_udev_create_context(ctypes.byref(self._iface), None, handle)
        udev.udev_unref(handle)  # the context holds its own reference
        if not ctx:
            raise OSError("libinput_udev_create_context failed")
        if li.libinput_udev_assign_seat(ctx, seat.encode()) != 0:
            li.libinput_unref(ctx)
            raise OSError(f"libinput cannot assign seat {seat}")
        self._ctx = ctx

    def fd(self) -> int:
        return self._li.libinput_get_fd(self._ctx)

    # 0, or a negative errno.
    def dispatch(self) -> int:
        return self._li.libinput_dispatch(self._ctx)

    def read_event(self) -> LibinputEvent | None:
        li = self._li
        event = li.libinput_get_event(self._ctx)
        if not event:
            return None
        try:
            kind = li.libinput_event_get_type(event)
            if kind in (DEVICE_ADDED, DEVICE_REMOVED):
                device = li.libinput_event_get_device(event)
                return LibinputEvent(
                    type=kind,
                    device=device,
                    keyboard=bool(li.libinput_device_has_capability(device, _CAP_KEYBOARD)),
                    pointer=bool(li.libinput_device_has_capability(device, _CAP_POINTER)),
                    name=(li.libinput_device_get_name(device) or b"").decode(errors="replace"),
                )
            if kind == KEYBOARD_KEY:
                key = li.libinput_event_get_keyboard_event(event)
                return LibinputEvent(
                    type=kind,
                    code=li.libinput_event_keyboard_get_key(key),
                    seat_count=li.libinput_event_keyboard_get_seat_key_count(key),
                )
            if kind == POINTER_BUTTON:
                pointer = li.libinput_event_get_pointer_event(event)
                return LibinputEvent(
                    type=kind,
                    code=li.libinput_event_pointer_get_button(pointer),
                    seat_count=li.libinput_event_pointer_get_seat_button_count(pointer),
                )
            return LibinputEvent(type=kind)
        finally:
            li.libinput_event_destroy(event)

    # Closes every device through close_restricted; the callbacks stay referenced until the object dies.
    def close(self) -> None:
        if self._ctx is not None:
            self._li.libinput_unref(self._ctx)
            self._ctx = None
