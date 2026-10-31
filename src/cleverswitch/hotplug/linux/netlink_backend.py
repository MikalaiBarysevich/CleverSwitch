import errno
import logging
import os
import select
import socket
import threading

from ...errors.errors import HotplugError
from ...event.hid_node_added_event import HidNodeAddedEvent
from ...event.hid_node_removed_event import HidNodeRemovedEvent
from ...event.hotplug_resync_event import HotplugResyncEvent
from ...topic.topics import Topics
from ..backend import HotplugBackend
from .udev_message import ACTION_ADD, hidraw_event, sender_uid

log = logging.getLogger(__name__)

_NETLINK_KOBJECT_UEVENT = 15

# udevd's group: sent after rules ran, so the uaccess ACL is already on the node
_UDEV_GROUP = 2

_RECEIVE_BUFFER = 1 << 20
_MESSAGE_SIZE = 16384
_STOP_JOIN_TIMEOUT = 2.0


class NetlinkHotplugBackend(HotplugBackend):
    def __init__(self, topics: Topics) -> None:
        self._topics = topics
        self._sock: socket.socket | None = None
        self._wake_read: int | None = None
        self._wake_write: int | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        try:
            sock = socket.socket(socket.AF_NETLINK, socket.SOCK_RAW | socket.SOCK_CLOEXEC, _NETLINK_KOBJECT_UEVENT)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, _RECEIVE_BUFFER)
            except OSError:
                pass
            sock.bind((0, _UDEV_GROUP))
        except OSError as e:
            raise HotplugError(f"Cannot listen for udev device events: {e}") from e
        self._sock = sock
        self._wake_read, self._wake_write = os.pipe()
        self._thread = threading.Thread(target=self._run, name="hotplug-udev", daemon=True)
        self._thread.start()
        log.info("Listening for device hotplug events from udev")

    def stop(self) -> None:
        thread, self._thread = self._thread, None
        if thread is None:
            return
        os.write(self._wake_write, b"\x00")
        thread.join(timeout=_STOP_JOIN_TIMEOUT)
        self._sock.close()
        os.close(self._wake_read)
        os.close(self._wake_write)

    def _run(self) -> None:
        while True:
            readable, _, _ = select.select([self._sock, self._wake_read], [], [])
            if self._wake_read in readable:
                return
            try:
                data, ancdata, _flags, _address = self._sock.recvmsg(_MESSAGE_SIZE, socket.CMSG_SPACE(12))
            except OSError as e:
                if e.errno == errno.ENOBUFS:
                    log.warning("udev events were lost; re-checking every device")
                    self._topics.hotplug.publish(HotplugResyncEvent(slot=0, pid=0))
                    continue
                log.error(f"udev event socket failed, device hotplug stopped: {e}")
                return
            self._handle(data, ancdata)

    def _handle(self, data: bytes, ancdata) -> None:
        if sender_uid(ancdata) != 0:
            return
        parsed = hidraw_event(data)
        if parsed is None:
            return
        action, pid = parsed
        event_type = HidNodeAddedEvent if action == ACTION_ADD else HidNodeRemovedEvent
        self._topics.hotplug.publish(event_type(slot=0, pid=pid))
