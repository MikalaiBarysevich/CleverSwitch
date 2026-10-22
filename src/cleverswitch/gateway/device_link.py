import logging

from ..event.write_event import WriteEvent
from ..gateway.hid_gateway import HidGateway
from ..gateway.write_router import WriteRouter
from ..listener.event_listener import EventListener
from ..subscriber.subscriber import Subscriber
from ..topic.topics import Topics

log = logging.getLogger(__name__)


class DeviceLink(Subscriber):
    """Everything CleverSwitch holds open for one HID product id.

    Owns the device's HID collection gateways and their shared EventListener, and is the only
    write-topic subscriber for that pid: each outbound message goes to the one gateway its
    WriteRouter selects.
    """

    def __init__(
        self,
        pid: int,
        topics: Topics,
        listener: EventListener,
        gateways: list[HidGateway],
        router: WriteRouter,
    ) -> None:
        self._pid = pid
        self._listener = listener
        self._gateways = gateways
        self._router = router
        topics.write.subscribe(self)

    def notify(self, event) -> None:
        if not isinstance(event, WriteEvent) or event.pid != self._pid:
            return
        gateway = self._router.select(event.hid_message, self._gateways)
        if gateway is None:
            log.debug(f"No collection accepts report 0x{event.hid_message[0]:02X} for pid=0x{self._pid:04X}")
            return
        gateway.submit(event.hid_message)

    def start(self) -> None:
        for gateway in self._gateways:
            gateway.start()
        self._listener.start()

    def close(self) -> None:
        for gateway in self._gateways:
            gateway.close()
