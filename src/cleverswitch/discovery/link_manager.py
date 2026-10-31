import logging
import threading
from collections.abc import Callable

from ..event.hid_node_added_event import HidNodeAddedEvent
from ..event.hid_node_removed_event import HidNodeRemovedEvent
from ..event.hotplug_resync_event import HotplugResyncEvent
from ..gateway.device_link import DeviceLink
from ..hidpp.transport import HidDeviceInfo, enumerate_hid_devices
from ..subscriber.subscriber import Subscriber
from ..topic.topics import Topics
from .link_factory import create_link

log = logging.getLogger(__name__)


class LinkManager(Subscriber):
    """Owns one DeviceLink per HID product id. Every hotplug event re-enumerates its product id and
    hands the link what is listed now; the event only says where to look."""

    def __init__(
        self,
        topics: Topics,
        verbose_extra: bool = False,
        link_factory: Callable[[int, list[HidDeviceInfo], Topics], DeviceLink] = create_link,
        enumerate_devices: Callable[..., dict[int, list[HidDeviceInfo]]] = enumerate_hid_devices,
    ) -> None:
        self._topics = topics
        self._verbose_extra = verbose_extra
        self._link_factory = link_factory
        self._enumerate = enumerate_devices
        self._links: dict[int, DeviceLink] = {}
        self._closed = False
        self._lock = threading.Lock()
        topics.hotplug.subscribe(self)

    def notify(self, event) -> None:
        if isinstance(event, HotplugResyncEvent):
            self._resync()
        elif isinstance(event, (HidNodeAddedEvent, HidNodeRemovedEvent)):
            action = "added" if isinstance(event, HidNodeAddedEvent) else "removed"
            log.debug(f"HID node {action} for pid=0x{event.pid:04X}")
            found = self._enumerate(product_id=event.pid, verbose_extra=self._verbose_extra)
            self._reconcile(event.pid, found.get(event.pid, []))

    def _resync(self) -> None:
        found = self._enumerate(verbose_extra=self._verbose_extra)
        with self._lock:
            pids = set(found) | set(self._links)
        for pid in sorted(pids):
            self._reconcile(pid, found.get(pid, []))

    def _reconcile(self, pid: int, collections: list[HidDeviceInfo]) -> None:
        with self._lock:
            if self._closed:
                return
            link = self._links.get(pid)
            if link is not None:
                link.update(collections)
                return
            if not collections:
                return
            link = self._link_factory(pid, collections, self._topics)
            self._links[pid] = link
            link.start()

    def close_all(self) -> None:
        with self._lock:
            self._closed = True
            links = list(self._links.values())
        for link in links:
            link.close()
