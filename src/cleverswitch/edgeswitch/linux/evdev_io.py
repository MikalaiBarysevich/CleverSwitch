import errno
import glob
import os
import select

_KEY_STATE_BYTES = 96  # KEY_MAX (0x2ff) / 8 + 1
_EVIOCGRAB = 0x40044590  # _IOW('E', 0x90, int)
_READ_EVENTS = 64


def _eviocgkey(length: int) -> int:
    return (2 << 30) | (length << 16) | (ord("E") << 8) | 0x18  # _IOR('E', 0x18, len)


class EvdevIO:
    """Listen-only access to /dev/input: no EVIOCGRAB, so every other reader still gets every event."""

    def list_nodes(self) -> list[str]:
        return sorted(glob.glob("/dev/input/event*"))

    # (key, rel) capability bitmaps from sysfs; empty strings when unreadable.
    def read_caps(self, node: str) -> tuple[str, str]:
        base = f"/sys/class/input/{os.path.basename(node)}/device/capabilities"
        return self._read_text(f"{base}/key"), self._read_text(f"{base}/rel")

    def device_name(self, node: str) -> str:
        return self._read_text(f"/sys/class/input/{os.path.basename(node)}/device/name") or node

    def open(self, node: str) -> int:
        return os.open(node, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)

    def key_state(self, fd: int) -> bytes:
        import fcntl

        buffer = bytearray(_KEY_STATE_BYTES)
        fcntl.ioctl(fd, _eviocgkey(_KEY_STATE_BYTES), buffer)
        return bytes(buffer)

    # Another reader's exclusive grab makes EVIOCGRAB fail with EBUSY. A free device is grabbed and
    # released at once, so its other readers miss at most the events of that instant.
    def is_grabbed(self, fd: int) -> bool:
        import fcntl

        try:
            fcntl.ioctl(fd, _EVIOCGRAB, 1)
        except OSError as e:
            return e.errno == errno.EBUSY
        fcntl.ioctl(fd, _EVIOCGRAB, 0)
        return False

    # b"" when nothing is pending; OSError (ENODEV) once the device is gone.
    def read(self, fd: int, event_size: int) -> bytes:
        try:
            return os.read(fd, event_size * _READ_EVENTS)
        except BlockingIOError:
            return b""
        except OSError as e:
            if e.errno == errno.EINTR:
                return b""
            raise

    def close(self, fd: int) -> None:
        try:
            os.close(fd)
        except OSError:
            pass

    def pipe(self) -> tuple[int, int]:
        return os.pipe()

    def wake(self, fd: int) -> None:
        os.write(fd, b"x")

    def poll(self, fds: list[int], timeout_ms: int) -> list[int]:
        poller = select.poll()
        for fd in fds:
            poller.register(fd, select.POLLIN)
        return [fd for fd, _mask in poller.poll(timeout_ms)]

    def _read_text(self, path: str) -> str:
        try:
            with open(path) as f:
                return f.read().strip()
        except OSError:
            return ""
