import logging

from .errors import TransportError
from .hidpp.constants import HOST_SWITCH_CIDS
from .hidpp.protocol import send_change_host, set_cid_divert
from .hidpp.transport import HIDTransport
from .model import ConnectionEvent, EventProcessorArguments, ExternalUndivertEvent, HostChangeEvent, LogiProduct

log = logging.getLogger(__name__)


class Processor:
    def process(self, arguments: EventProcessorArguments) -> None: ...


class ConnectionProcessor(Processor):
    def process(self, arguments: EventProcessorArguments) -> None:
        event = arguments.event
        if not isinstance(event, ConnectionEvent):
            return

        product = arguments.products[arguments.event.slot]
        log.debug(f"Product reconnected slot={product.slot} name={product.name}")

        if product.divert_feat_idx is not None:
            log.debug(f"Sending divert host switch keys request for slot={product.slot} name={product.name}")
            _divert_all_es_keys(arguments.transport, product)


class ExternalUndivertProcessor(Processor):
    def process(self, arguments: EventProcessorArguments) -> None:
        event = arguments.event
        if not isinstance(event, ExternalUndivertEvent):
            return

        product = arguments.products[arguments.event.slot]
        cid = event.target_host_cid

        if product.divert_feat_idx is not None:
            log.debug(f"Sending single divert request slot={product.slot} name={product.name} cid={hex(cid)}")
            _divert_single_es_key(arguments.transport, product, cid)


class HostChangeProcessor(Processor):
    def process(self, arguments: EventProcessorArguments) -> None:
        if not isinstance(arguments.event, HostChangeEvent):
            return

        for product in arguments.products.values():
            log.debug("Sending host change event to: %s", product.name)
            # in case on first command the device is sleep the second switch should do the trick
            _switch(arguments.transport, product, arguments.event.target_host)


def _divert_all_es_keys(transport: HIDTransport, product: LogiProduct) -> None:
    for cid in HOST_SWITCH_CIDS:
        _divert_single_es_key(transport, product, cid)


def _divert_single_es_key(transport: HIDTransport, product: LogiProduct, cid: int) -> None:
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
