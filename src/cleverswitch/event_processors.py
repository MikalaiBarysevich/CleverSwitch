import logging
from enum import Enum
from typing import TypeVar

from cleverswitch.errors import TransportError
from cleverswitch.hidpp.constants import HOST_SWITCH_CIDS
from cleverswitch.hidpp.protocol import send_change_host, set_cid_divert
from cleverswitch.hidpp.transport import HIDTransport

from .model import (
    BaseEvent,
    DjConnectionEvent,
    EventProcessorArguments,
    HidConnectionEvent,
    HostChangeEvent,
    LogiProduct,
)

log = logging.getLogger(__name__)


class ConnectionState(Enum):
    CONNECTED = 0
    DISCONNECTED = 1


T = TypeVar("T", bound="BaseEvent")


class Processor:
    def process(self, arguments: EventProcessorArguments) -> None: ...


class BaseConnectionProcessor(Processor):
    def process(self, arguments: EventProcessorArguments) -> None:
        event = arguments.event
        if not self.should_process(event):
            return

        product = arguments.products[arguments.event.slot]
        if self.get_connection_state(event, product) == ConnectionState.CONNECTED:
            product.connected = True
            if product.divert_feat_idx is not None:
                _divert_all_es_keys(arguments.transport, product)
        else:
            product.connected = False

    def should_process(self, event: BaseEvent) -> bool | None: ...

    def get_connection_state(self, event: BaseEvent, product: LogiProduct) -> ConnectionState: ...


class ConnectionProcessor(Processor):
    def process(self, arguments: EventProcessorArguments) -> None:
        event = arguments.event
        if not isinstance(event, (DjConnectionEvent, HidConnectionEvent)):
            return

        product = arguments.products[arguments.event.slot]

        if isinstance(event, DjConnectionEvent):
            connection_state = (
                ConnectionState.CONNECTED if event.connection_status == 0 else ConnectionState.DISCONNECTED
            )
        else:
            connection_state = ConnectionState.CONNECTED if not product.connected else ConnectionState.DISCONNECTED

        if connection_state == ConnectionState.CONNECTED:
            product.connected = True
            if product.divert_feat_idx is not None:
                _divert_all_es_keys(arguments.transport, product)
        else:
            product.connected = False


class DjConnectionProcessor(BaseConnectionProcessor):
    def should_process(self, event: BaseEvent) -> bool | None:
        return isinstance(event, DjConnectionEvent)

    def get_connection_state(self, event: DjConnectionEvent, product: LogiProduct) -> ConnectionState:
        if event.connection_status == 0:
            return ConnectionState.CONNECTED
        return ConnectionState.DISCONNECTED


class HidConnectionProcessor(BaseConnectionProcessor):
    def should_process(self, event: BaseEvent) -> bool | None:
        return isinstance(event, HidConnectionEvent)

    def get_connection_state(self, event: HidConnectionEvent, product: LogiProduct) -> ConnectionState:
        if not product.connected:
            return ConnectionState.CONNECTED
        return ConnectionState.DISCONNECTED


class HostChangeProcessor(Processor):
    def process(self, arguments: EventProcessorArguments) -> None:
        if not isinstance(arguments.event, HostChangeEvent):
            return

        for product in arguments.products.values():
            _switch(arguments.transport, product, arguments.event.target_host)


def _divert_all_es_keys(transport: HIDTransport, product: LogiProduct) -> None:
    for cid in HOST_SWITCH_CIDS:
        try:
            set_cid_divert(transport, product.slot, product.divert_feat_idx, cid, True)
        except TransportError as e:
            log.warning("Failed to divert CID 0x%04X on %s: %s", cid, product.name, e)


def _switch(transport: HIDTransport, device: LogiProduct, target_host: int) -> None:
    send_change_host(
        transport,
        device.slot,
        device.change_host_feat_idx,
        target_host,
    )
