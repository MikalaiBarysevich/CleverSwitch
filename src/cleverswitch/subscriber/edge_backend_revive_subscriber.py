from ..edgeswitch.backend import EdgeBackend
from ..event.device_connected_event import DeviceConnectedEvent
from ..subscriber.subscriber import Subscriber
from ..topic.topics import Topics


class EdgeBackendReviveSubscriber(Subscriber):
    """Restarts edge switch after its input source was lost (X server gone, event tap revoked) when a device
    connects, instead of retrying on a timer. Usually that is the user coming back to this host."""

    def __init__(self, backend: EdgeBackend, topics: Topics):
        self._backend = backend
        topics.hid_event.subscribe(self)

    def notify(self, event) -> None:
        if isinstance(event, DeviceConnectedEvent) and event.link_established:
            self._backend.revive()
