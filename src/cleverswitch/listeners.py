import logging
import threading
from threading import Thread

from .errors import TransportError
from .event_processors import ConnectionProcessor, ExternalUndivertProcessor, HostChangeProcessor
from .factory import _make_logi_product
from .hidpp.constants import (
    BOLT_PID,
    DEVICE_TYPE_KEYBOARD,
    DEVICE_TYPE_MOUSE,
    DEVICE_TYPE_TRACKBALL,
    DEVICE_TYPE_TRACKPAD,
    FEATURE_DEVICE_TYPE_AND_NAME,
    HOST_SWITCH_CIDS,
    REPORT_LONG,
    SW_ID,
)
from .hidpp.protocol import get_device_name, get_device_type, resolve_feature_index, set_cid_divert
from .hidpp.transport import HidDeviceInfo, HIDTransport
from .model import (
    BaseEvent,
    ConnectionEvent,
    EventProcessorArguments,
    ExternalUndivertEvent,
    HostChangeEvent,
    LogiProduct,
)

log = logging.getLogger(__name__)


class PathListener(Thread):
    def __init__(self, hid_device_info: HidDeviceInfo, shutdown: threading.Event) -> None:
        self._hid_device_info = hid_device_info
        self._shutdown = shutdown
        self._transport: HIDTransport | None = None
        self._products: dict[int, LogiProduct] = {}
        self._event_processors = [
            ConnectionProcessor(),
            HostChangeProcessor(),
            ExternalUndivertProcessor(),
        ]
        self._stopped = False
        super().__init__()

    def run(self) -> None:
        self.init_transport()

        if self._transport is None:
            return

        self.detect_products()

        try:
            while not self._shutdown.is_set() and not self._stopped:
                raw = self._transport.read(100)

                if raw is None:
                    continue

                event = parse_message(raw, self._products)
                log.debug("parsed event=%s", event)

                if event is None:
                    continue

                if isinstance(event, ConnectionEvent) and event.slot not in self._products.keys():
                    log.debug("Adding product for slot=%d", event.slot)
                    self.add_new_product(event.slot)

                self.process_event(event)

                self._shutdown.wait(0.2)
        except TransportError as e:
            log.debug("Error occurred during processing event: %s", e)
        finally:
            for product in self._products.values():
                if product.divert_feat_idx is not None:
                    _undivert_all_es_keys(self._transport, product)
            self._transport.close()

    def init_transport(self) -> None:
        if self._transport is not None:
            return

        last_error = None

        for _i in range(3):
            try:
                hid_device = self._hid_device_info
                kind = "bolt" if hid_device.pid == BOLT_PID else "unifying"
                self._transport = HIDTransport(hid_device.path, kind, hid_device.pid)
                break
            except OSError as e:
                last_error = e
                log.debug(f"Error during transport init. Retry in 1 second. error={e}")
                self._shutdown.wait(1)

        if self._transport is None:
            log.debug(f"Couldn't open transport. error={last_error}")

    def detect_products(self) -> None:

        for slot in range(1, 7):
            if slot not in self._products:
                self.add_new_product(slot)
                if slot in self._products:
                    self.process_event(ConnectionEvent(slot))

    def process_event(self, event):
        for processor in self._event_processors:
            processor.process(
                EventProcessorArguments(
                    products=self._products,
                    transport=self._transport,
                    event=event,
                    shutdown=self._shutdown,
                )
            )

    def add_new_product(self, slot) -> None:
        try:
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
        except RuntimeError as e:
            log.debug("Error occurred during adding new product: %s", e)
            if slot in self._products:
                self._products.pop(slot)

    def stop(self):
        self._stopped = True


def parse_message(raw: bytes, products: dict[int, LogiProduct] | None = None) -> BaseEvent | None:
    """Parse a raw HID++ packet into a structured event, or None if irrelevant.

    When *products* is provided, also detects setCidReporting responses from
    other applications (e.g. Solaar) that undivert Easy-Switch keys, returning
    a ConnectionEvent to trigger re-diversion.
    """
    if not raw or len(raw) < 4:
        return None

    log.debug("Attempt to parse raw data=: %s", raw.hex())

    report_id = raw[0]
    slot = raw[1]
    feature_id = raw[2]
    function_id = raw[3]

    if report_id != REPORT_LONG:
        return None

    if feature_id == 0x04 and raw[4] == 0x01:
        return ConnectionEvent(slot)

    if products is None:
        products = {}
    divert_feat_idx = products[slot].divert_feat_idx if slot in products else None
    target_host_cid = raw[5]

    cid_reporting_fn = function_id & 0xF0
    software_id = function_id & 0x0F
    if (
        feature_id == divert_feat_idx
        and cid_reporting_fn == 0x30
        and software_id not in (0, SW_ID)
        and target_host_cid in HOST_SWITCH_CIDS
    ):
        return ExternalUndivertEvent(slot, target_host_cid)

    if (
        function_id == 0x00
        and feature_id == divert_feat_idx
        and target_host_cid
        and target_host_cid in HOST_SWITCH_CIDS
    ):
        return HostChangeEvent(slot, HOST_SWITCH_CIDS[target_host_cid])

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
