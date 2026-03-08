import logging

from .errors import TransportError
from .hidpp.constants import HOST_SWITCH_CIDS
from .hidpp.protocol import send_change_host, set_cid_divert
from .hidpp.transport import HIDTransport
from .model import ConnectionEvent, EventProcessorArguments, HostChangeEvent, LogiProduct

log = logging.getLogger(__name__)


class Processor:
    def process(self, arguments: EventProcessorArguments) -> None: ...


class ConnectionProcessor(Processor):
    def process(self, arguments: EventProcessorArguments) -> None:
        event = arguments.event
        if not isinstance(event, ConnectionEvent):
            return

        product = arguments.products[arguments.event.slot]

        if product.divert_feat_idx is not None:
            _divert_all_es_keys(arguments.transport, product)


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
