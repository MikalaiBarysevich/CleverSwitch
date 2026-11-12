import logging

from ..event.edge_touched_event import EdgeTouchedEvent
from ..event.host_change_event import HostChangeEvent, SwitchSource
from ..model.config.edge_switch_config import EdgeSwitchConfig
from ..model.switch_echo_guard import SwitchEchoGuard
from ..subscriber.subscriber import Subscriber
from ..topic.topics import Topics

log = logging.getLogger(__name__)


class EdgeSwitchSubscriber(Subscriber):
    """Maps a touched screen edge to its configured host and asks for a switch of every device."""

    def __init__(self, edge_switch_config: EdgeSwitchConfig, topics: Topics, echo_guard: SwitchEchoGuard):
        self._edges = edge_switch_config.edges
        self._topics = topics
        self._echo_guard = echo_guard
        topics.edge.subscribe(self)

    def notify(self, event) -> None:
        if not isinstance(event, EdgeTouchedEvent):
            return
        target_host = self._edges.get(event.edge)
        if target_host is None:
            return
        log.info(f"Edge '{event.edge}' reached → switching all devices to host {target_host + 1}")
        self._echo_guard.record(target_host)
        self._topics.hid_event.publish(
            HostChangeEvent(slot=0, pid=0, target_host=target_host, source=SwitchSource.EDGE)
        )
