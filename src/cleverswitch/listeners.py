import logging
import threading
from threading import Thread

from cleverswitch.errors import TransportError
from cleverswitch.event_processors import ConnectionProcessor, HostChangeProcessor
from cleverswitch.factory import _make_logi_product
from cleverswitch.hidpp.constants import (
    BOLT_PID,
    DEVICE_TYPE_KEYBOARD,
    DEVICE_TYPE_MOUSE,
    DEVICE_TYPE_TRACKBALL,
    DEVICE_TYPE_TRACKPAD,
    DJ_DEVICE_PAIRING,
    FEATURE_DEVICE_TYPE_AND_NAME,
    HID_DEVICE_PAIRING,
    HOST_SWITCH_CIDS,
    REPORT_DJ,
    REPORT_LONG,
    REPORT_SHORT,
)
from cleverswitch.hidpp.protocol import get_device_name, get_device_type, resolve_feature_index, set_cid_divert
from cleverswitch.hidpp.transport import HidDeviceInfo, HIDTransport
from cleverswitch.model import (
    BaseEvent,
    DjConnectionEvent,
    EventProcessorArguments,
    HidConnectionEvent,
    HostChangeEvent,
    LogiProduct,
)

log = logging.getLogger(__name__)


class PathListener(Thread):
    def __init__(self, hid_device_info: HidDeviceInfo, shutdown: threading.Event) -> None:
        self._hid_device_info = hid_device_info
        self._shutdown = shutdown
        kind = "bolt" if hid_device_info.pid == BOLT_PID else "unifying"
        self._transport = HIDTransport(hid_device_info.path, kind, hid_device_info.pid)
        self._products: dict[int, LogiProduct] = {}
        self._event_processors = [
            ConnectionProcessor(),
            HostChangeProcessor(),
        ]
        self.detect_products()
        super().__init__()

    def detect_products(self) -> None:
        for slot in range(1, 7):
            self.add_new_product(slot)
            if slot in self._products:
                self.process_event(DjConnectionEvent(slot, 0))

    def process_event(self, event):
        for processor in self._event_processors:
            processor.process(
                EventProcessorArguments(
                    products=self._products,
                    transport=self._transport,
                    event=event,
                )
            )

    def run(self) -> None:
        try:
            while not self._shutdown.is_set():
                raw = self._transport.read(100)

                if raw is None:
                    # self._shutdown.wait(0.2)
                    continue

                event = parse_message(raw)
                log.debug("parsed event=%s", event)

                if event is None:
                    continue

                if (
                    isinstance(event, (DjConnectionEvent, HidConnectionEvent))
                    and event.slot not in self._products.keys()
                ):
                    log.info("adding product %d", event.slot)
                    self.add_new_product(event.slot)

                self.process_event(event)

                self._shutdown.wait(0.2)
        finally:
            for product in self._products.values():
                if product.divert_feat_idx is not None:
                    _undivert_all_es_keys(self._transport, product)
            self._transport.close()

    def add_new_product(self, slot) -> None:
        if slot in self._products:
            return
        log.debug("Receiver slot %d", slot)
        info = _query_device_info(self._transport, slot)

        if not info:
            return

        role, name = info
        product = _make_logi_product(self._transport, slot, role=role, name=name)
        if product:
            self._products[slot] = product


def parse_message(raw: bytes) -> BaseEvent | None:
    """Parse a raw HID++ packet into a structured event, or None if irrelevant."""
    if not raw or len(raw) < 4:
        return None

    log.debug("Attempt to parse raw data=: %s", raw)

    report_id = raw[0]
    slot = raw[1]
    feature_id = raw[2]
    address = raw[3]
    target_host_cid = raw[5]

    if report_id == REPORT_LONG and address == 0x00 and target_host_cid and target_host_cid in HOST_SWITCH_CIDS.keys():
        return HostChangeEvent(slot, HOST_SWITCH_CIDS[target_host_cid])

    if report_id == REPORT_DJ and feature_id == DJ_DEVICE_PAIRING:
        return DjConnectionEvent(slot, address)

    if report_id == REPORT_SHORT and feature_id == HID_DEVICE_PAIRING:
        return HidConnectionEvent(slot)

    return None


def _divert_all_es_keys(transport: HIDTransport, product: LogiProduct) -> None:
    for cid in HOST_SWITCH_CIDS:
        try:
            set_cid_divert(transport, product.slot, product.divert_feat_idx, cid, True)
        except TransportError as e:
            log.warning("Failed to divert CID 0x%04X on %s: %s", cid, product.name, e)


def _undivert_all_es_keys(transport: HIDTransport, product: LogiProduct) -> None:
    for cid in HOST_SWITCH_CIDS:
        try:
            set_cid_divert(transport, product.slot, product.divert_feat_idx, cid, False)
        except Exception:
            pass


def _query_device_info(transport: HIDTransport, devnumber: int) -> tuple[str, str] | None:
    """Query role and marketing name via x0005 DEVICE_TYPE_AND_NAME.

    Returns (role, name) where role is 'keyboard' or 'mouse'.
    Falls back to role as name if getDeviceName fails.
    Returns None if the feature is absent or device type is unrecognised.
    """
    feat_idx = resolve_feature_index(transport, devnumber, FEATURE_DEVICE_TYPE_AND_NAME)
    if feat_idx is None:
        return None
    device_type = get_device_type(transport, devnumber, feat_idx)
    role = _device_type_to_role(device_type)
    if role is None:
        return None
    name = get_device_name(transport, devnumber, feat_idx) or role
    return role, name


_MOUSE_DEVICE_TYPES = frozenset((DEVICE_TYPE_MOUSE, DEVICE_TYPE_TRACKBALL, DEVICE_TYPE_TRACKPAD))


def _device_type_to_role(device_type: int | None) -> str | None:
    """Map an x0005 deviceType value to 'keyboard', 'mouse', or None."""
    if device_type == DEVICE_TYPE_KEYBOARD:
        return "keyboard"
    if device_type in _MOUSE_DEVICE_TYPES:
        return "mouse"
    return None
