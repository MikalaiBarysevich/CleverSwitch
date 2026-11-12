import ctypes
import ctypes.util

_KEYMAP_BYTES = 32


class _Cookie(ctypes.Structure):
    _fields_ = [("sequence", ctypes.c_uint)]


class _ScreenIterator(ctypes.Structure):
    _fields_ = [("data", ctypes.c_void_p), ("rem", ctypes.c_int), ("index", ctypes.c_int)]


class _Setup(ctypes.Structure):
    _fields_ = [
        ("status", ctypes.c_uint8),
        ("pad0", ctypes.c_uint8),
        ("protocol_major_version", ctypes.c_uint16),
        ("protocol_minor_version", ctypes.c_uint16),
        ("length", ctypes.c_uint16),
        ("release_number", ctypes.c_uint32),
        ("resource_id_base", ctypes.c_uint32),
        ("resource_id_mask", ctypes.c_uint32),
        ("motion_buffer_size", ctypes.c_uint32),
        ("vendor_len", ctypes.c_uint16),
        ("maximum_request_length", ctypes.c_uint16),
        ("roots_len", ctypes.c_uint8),
        ("pixmap_formats_len", ctypes.c_uint8),
        ("image_byte_order", ctypes.c_uint8),
        ("bitmap_format_bit_order", ctypes.c_uint8),
        ("bitmap_format_scanline_unit", ctypes.c_uint8),
        ("bitmap_format_scanline_pad", ctypes.c_uint8),
        ("min_keycode", ctypes.c_uint8),
        ("max_keycode", ctypes.c_uint8),
        ("pad1", ctypes.c_uint8 * 4),
    ]


class _QueryPointerReply(ctypes.Structure):
    _fields_ = [
        ("response_type", ctypes.c_uint8),
        ("same_screen", ctypes.c_uint8),
        ("sequence", ctypes.c_uint16),
        ("length", ctypes.c_uint32),
        ("root", ctypes.c_uint32),
        ("child", ctypes.c_uint32),
        ("root_x", ctypes.c_int16),
        ("root_y", ctypes.c_int16),
        ("win_x", ctypes.c_int16),
        ("win_y", ctypes.c_int16),
        ("mask", ctypes.c_uint16),
        ("pad0", ctypes.c_uint8 * 2),
    ]


class _QueryKeymapReply(ctypes.Structure):
    _fields_ = [
        ("response_type", ctypes.c_uint8),
        ("pad0", ctypes.c_uint8),
        ("sequence", ctypes.c_uint16),
        ("length", ctypes.c_uint32),
        ("keys", ctypes.c_uint8 * _KEYMAP_BYTES),
    ]


class _GetGeometryReply(ctypes.Structure):
    _fields_ = [
        ("response_type", ctypes.c_uint8),
        ("depth", ctypes.c_uint8),
        ("sequence", ctypes.c_uint16),
        ("length", ctypes.c_uint32),
        ("root", ctypes.c_uint32),
        ("x", ctypes.c_int16),
        ("y", ctypes.c_int16),
        ("width", ctypes.c_uint16),
        ("height", ctypes.c_uint16),
        ("border_width", ctypes.c_uint16),
        ("pad0", ctypes.c_uint8 * 2),
    ]


class _GetKeyboardMappingReply(ctypes.Structure):
    _fields_ = [
        ("response_type", ctypes.c_uint8),
        ("keysyms_per_keycode", ctypes.c_uint8),
        ("sequence", ctypes.c_uint16),
        ("length", ctypes.c_uint32),
        ("pad0", ctypes.c_uint8 * 24),
    ]


class Xcb:
    """libxcb rather than Xlib: Xlib's default I/O error handler calls exit() when the X server goes
    away, which would take the daemon with it. xcb reports a lost connection through has_error()."""

    def __init__(self) -> None:
        xcb = ctypes.CDLL(ctypes.util.find_library("xcb") or "libxcb.so.1")
        libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6")
        p = ctypes.c_void_p

        xcb.xcb_connect.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
        xcb.xcb_connect.restype = p
        xcb.xcb_connection_has_error.argtypes = [p]
        xcb.xcb_connection_has_error.restype = ctypes.c_int
        xcb.xcb_disconnect.argtypes = [p]
        xcb.xcb_disconnect.restype = None
        xcb.xcb_get_setup.argtypes = [p]
        xcb.xcb_get_setup.restype = ctypes.POINTER(_Setup)
        xcb.xcb_setup_roots_iterator.argtypes = [ctypes.POINTER(_Setup)]
        xcb.xcb_setup_roots_iterator.restype = _ScreenIterator
        xcb.xcb_screen_next.argtypes = [ctypes.POINTER(_ScreenIterator)]
        xcb.xcb_screen_next.restype = None
        xcb.xcb_query_pointer.argtypes = [p, ctypes.c_uint32]
        xcb.xcb_query_pointer.restype = _Cookie
        xcb.xcb_query_pointer_reply.argtypes = [p, _Cookie, p]
        xcb.xcb_query_pointer_reply.restype = ctypes.POINTER(_QueryPointerReply)
        xcb.xcb_query_keymap.argtypes = [p]
        xcb.xcb_query_keymap.restype = _Cookie
        xcb.xcb_query_keymap_reply.argtypes = [p, _Cookie, p]
        xcb.xcb_query_keymap_reply.restype = ctypes.POINTER(_QueryKeymapReply)
        xcb.xcb_get_geometry.argtypes = [p, ctypes.c_uint32]
        xcb.xcb_get_geometry.restype = _Cookie
        xcb.xcb_get_geometry_reply.argtypes = [p, _Cookie, p]
        xcb.xcb_get_geometry_reply.restype = ctypes.POINTER(_GetGeometryReply)
        xcb.xcb_get_keyboard_mapping.argtypes = [p, ctypes.c_uint8, ctypes.c_uint8]
        xcb.xcb_get_keyboard_mapping.restype = _Cookie
        xcb.xcb_get_keyboard_mapping_reply.argtypes = [p, _Cookie, p]
        xcb.xcb_get_keyboard_mapping_reply.restype = ctypes.POINTER(_GetKeyboardMappingReply)
        xcb.xcb_get_keyboard_mapping_keysyms.argtypes = [ctypes.POINTER(_GetKeyboardMappingReply)]
        xcb.xcb_get_keyboard_mapping_keysyms.restype = ctypes.POINTER(ctypes.c_uint32)
        xcb.xcb_get_keyboard_mapping_keysyms_length.argtypes = [ctypes.POINTER(_GetKeyboardMappingReply)]
        xcb.xcb_get_keyboard_mapping_keysyms_length.restype = ctypes.c_int
        libc.free.argtypes = [p]
        libc.free.restype = None
        self._xcb = xcb
        self._libc = libc

        screen_number = ctypes.c_int(0)
        conn = xcb.xcb_connect(None, ctypes.byref(screen_number))
        if not conn or xcb.xcb_connection_has_error(conn):
            if conn:
                xcb.xcb_disconnect(conn)
            raise OSError("cannot connect to the X server")
        self._conn = conn

        setup = xcb.xcb_get_setup(conn)
        iterator = xcb.xcb_setup_roots_iterator(setup)
        for _ in range(screen_number.value):
            xcb.xcb_screen_next(ctypes.byref(iterator))
        self._root = ctypes.c_uint32.from_address(iterator.data).value  # xcb_screen_t starts with root
        self._min_keycode = setup.contents.min_keycode
        self._max_keycode = setup.contents.max_keycode

    def has_error(self) -> bool:
        return bool(self._xcb.xcb_connection_has_error(self._conn))

    def query_pointer(self) -> tuple[int, int, int] | None:
        reply = self._xcb.xcb_query_pointer_reply(self._conn, self._xcb.xcb_query_pointer(self._conn, self._root), None)
        if not reply:
            return None
        try:
            return reply.contents.root_x, reply.contents.root_y, reply.contents.mask
        finally:
            self._libc.free(reply)

    def query_keymap(self) -> bytes | None:
        reply = self._xcb.xcb_query_keymap_reply(self._conn, self._xcb.xcb_query_keymap(self._conn), None)
        if not reply:
            return None
        try:
            return bytes(reply.contents.keys)
        finally:
            self._libc.free(reply)

    def root_geometry(self) -> tuple[int, int, int, int] | None:
        reply = self._xcb.xcb_get_geometry_reply(self._conn, self._xcb.xcb_get_geometry(self._conn, self._root), None)
        if not reply:
            return None
        try:
            g = reply.contents
            return g.x, g.y, g.width, g.height
        finally:
            self._libc.free(reply)

    # (keysyms per keycode, first keycode, keysyms) for every keycode the server knows.
    def keyboard_mapping(self) -> tuple[int, int, list[int]] | None:
        count = self._max_keycode - self._min_keycode + 1
        cookie = self._xcb.xcb_get_keyboard_mapping(self._conn, self._min_keycode, count)
        reply = self._xcb.xcb_get_keyboard_mapping_reply(self._conn, cookie, None)
        if not reply:
            return None
        try:
            length = self._xcb.xcb_get_keyboard_mapping_keysyms_length(reply)
            keysyms = self._xcb.xcb_get_keyboard_mapping_keysyms(reply)
            return reply.contents.keysyms_per_keycode, self._min_keycode, keysyms[:length]
        finally:
            self._libc.free(reply)

    def close(self) -> None:
        self._xcb.xcb_disconnect(self._conn)
