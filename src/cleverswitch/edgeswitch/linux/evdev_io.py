import errno
import glob
import os
import select

from ...hotplug.linux.udev_socket import open_udev_socket, receive

_KEY_STATE_BYTES = 96  # KEY_MAX (0x2ff) / 8 + 1
_READ_EVENTS = 64


def _eviocgkey(length: int) -> int:
    return (2 << 30) | (length << 16) | (ord("E") << 8) | 0x18  # _IOR('E', 0x18, len)


class EvdevIO:
    """Listen-only access to /dev/input: no EVIOCGRAB, so every other reader still gets every event."""

    def __init__(self) -> None:
        self._udev = None

    # udevd's add/change/remove messages; the fd to poll.
    def open_udev(self) -> int:
        self._udev = open_udev_socket()
        self._udev.setblocking(False)
        return self._udev.fileno()

    # (message, credentials), None when nothing is pending; OSError ENOBUFS when messages were lost.
    def receive_udev(self) -> tuple[bytes, list] | None:
        try:
            return receive(self._udev)
        except BlockingIOError:
            return None

    def close_udev(self) -> None:
        if self._udev is not None:
            self._udev.close()
            self._udev = None

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
