import logging
from collections.abc import Callable

from ...errors.errors import HotplugError
from ...event.hid_node_added_event import HidNodeAddedEvent
from ...event.hid_node_removed_event import HidNodeRemovedEvent
from ...topic.topics import Topics
from ..backend import HotplugBackend
from .cfgmgr32 import ACTION_INTERFACE_ARRIVAL, ACTION_INTERFACE_REMOVAL, ERROR_SUCCESS, CfgMgr32, NotifyCallback
from .interface_name import hid_interface_pid

log = logging.getLogger(__name__)


class CfgMgrHotplugBackend(HotplugBackend):
    """Listens for HID interface arrival and removal through CM_Register_Notification. Windows runs
    the callback on its own thread pool, so no thread of ours is needed."""

    def __init__(self, topics: Topics, cfgmgr_factory: Callable[[], CfgMgr32] = CfgMgr32) -> None:
        self._topics = topics
        self._cfgmgr_factory = cfgmgr_factory
        self._cfgmgr: CfgMgr32 | None = None
        self._handle: int | None = None
        self._callback = NotifyCallback(self._on_notification)

    def start(self) -> None:
        try:
            self._cfgmgr = self._cfgmgr_factory()
            self._handle = self._cfgmgr.register_hid_interfaces(self._callback)
        except Exception as e:
            raise HotplugError(f"Cannot listen for Windows device events: {e}") from e
        log.info("Listening for device hotplug events from CfgMgr32")

    # CM_Unregister_Notification waits for callbacks in flight, so this must never run on one.
    def stop(self) -> None:
        handle, self._handle = self._handle, None
        if handle is not None:
            self._cfgmgr.unregister(handle)

    def _on_notification(self, _notify, _context, action: int, event_data: int, _size: int) -> int:
        try:
            self._publish(action, self._cfgmgr.symbolic_link(event_data))
        except Exception:
            log.exception("Cannot handle a Windows device notification")
        return ERROR_SUCCESS

    def _publish(self, action: int, symbolic_link: str) -> None:
        if action == ACTION_INTERFACE_ARRIVAL:
            event_type = HidNodeAddedEvent
        elif action == ACTION_INTERFACE_REMOVAL:
            event_type = HidNodeRemovedEvent
        else:
            return
        pid = hid_interface_pid(symbolic_link)
        if pid is not None:
            self._topics.hotplug.publish(event_type(slot=0, pid=pid))
