import logging
import threading
from threading import Thread

from .errors import TransportError
from .factory import _make_logi_product
from .hidpp.constants import (
    BOLT_PID,
    DEVICE_RECEIVER,
    DEVICE_TYPE_KEYBOARD,
    DEVICE_TYPE_MOUSE,
    DEVICE_TYPE_TRACKBALL,
    DEVICE_TYPE_TRACKPAD,
    FEATURE_DEVICE_TYPE_AND_NAME,
    HOST_SWITCH_CIDS,
    REPORT_LONG,
    SW_ID,
)
from .hidpp.protocol import get_device_name, get_device_type, resolve_feature_index, send_change_host, set_cid_divert
from .hidpp.transport import HidDeviceInfo, HIDTransport
from .model import (
    BaseEvent,
    ConnectionEvent,
    ExternalUndivertEvent,
    HostChangeEvent,
    LogiProduct,
    ProductEntry,
)

log = logging.getLogger(__name__)


# ── Product registry ─────────────────────────────────────────────────────────

# Key: (receiver_path, slot) for receiver devices, pid (int) for BT devices
ProductKey = tuple[bytes, int] | int


class ProductRegistry:
    """Thread-safe registry of all known products across all connection types."""

    def __init__(self):
        self._lock = threading.Lock()
        self._products: dict[ProductKey, ProductEntry] = {}

    def register(self, key: ProductKey, entry: ProductEntry) -> None:
        with self._lock:
            self._products[key] = entry

    def unregister(self, key: ProductKey) -> None:
        with self._lock:
            self._products.pop(key, None)

    def all_entries(self) -> list[ProductEntry]:
        with self._lock:
            return list(self._products.values())


# ── Base listener ────────────────────────────────────────────────────────────


class BaseListener(Thread):
    """Common event loop: open transport, read packets, parse, dispatch."""

    def __init__(self, hid_device_info: HidDeviceInfo, shutdown: threading.Event, registry: ProductRegistry) -> None:
        self._hid_device_info = hid_device_info
        self._shutdown = shutdown
        self._registry = registry
        self._transport: HIDTransport | None = None
        self._products: dict[int, LogiProduct] = {}
        self._stopped = False
        super().__init__(daemon=True)

    def run(self) -> None:
        self._init_transport()
        if self._transport is None:
            return
        self._detect_products()
        try:
            self._event_loop()
        except TransportError as e:
            log.debug("Transport error on %s: %s", self._hid_device_info.path, e)
        finally:
            self._cleanup()

    def _event_loop(self) -> None:
        while not self._shutdown.is_set() and not self._stopped:
            raw = self._transport.read(100)
            if raw is None:
                continue
            event = parse_message(raw, self._products)
            log.debug("parsed event=%s", event)
            if event is None:
                continue
            self._handle_event(event)
            self._shutdown.wait(0.2)

    def _handle_host_change(self, event: HostChangeEvent) -> None:
        """Send CHANGE_HOST to ALL products in the registry."""
        for entry in self._registry.all_entries():
            log.debug("Sending host change event to: %s", entry.name)
            try:
                send_change_host(entry.transport, entry.devnumber, entry.change_host_feat_idx, event.target_host)
            except Exception as e:
                log.debug("Host switch failed for %s: %s", entry.name, e)

    def _init_transport(self) -> None: ...

    def _detect_products(self) -> None: ...

    def _handle_event(self, event: BaseEvent) -> None: ...

    def _cleanup(self) -> None:
        if self._transport is not None:
            self._transport.close()

    def stop(self) -> None:
        self._stopped = True


# ── Receiver listener ────────────────────────────────────────────────────────


class ReceiverListener(BaseListener):
    """Handles a Bolt/Unifying receiver with devices in slots 1-6."""

    def _init_transport(self) -> None:
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

    def _detect_products(self) -> None:
        for slot in range(1, 7):
            if slot not in self._products:
                self._add_product(slot)
                if slot in self._products:
                    self._handle_connection(ConnectionEvent(slot))

    def _handle_event(self, event: BaseEvent) -> None:
        if isinstance(event, ConnectionEvent):
            if event.slot not in self._products:
                log.debug("Adding product for slot=%d", event.slot)
                self._add_product(event.slot)
            self._handle_connection(event)
        elif isinstance(event, HostChangeEvent):
            self._handle_host_change(event)
        elif isinstance(event, ExternalUndivertEvent):
            self._handle_external_undivert(event)

    def _handle_connection(self, event: ConnectionEvent) -> None:
        product = self._products.get(event.slot)
        if product is None:
            return
        log.debug(f"Product reconnected slot={product.slot} name={product.name}")
        if product.divert_feat_idx is not None:
            log.debug(f"Sending divert host switch keys request for slot={product.slot} name={product.name}")
            _divert_all_es_keys(self._transport, product)

    def _handle_external_undivert(self, event: ExternalUndivertEvent) -> None:
        product = self._products.get(event.slot)
        if product is None:
            return
        if product.divert_feat_idx is not None:
            cid = hex(event.target_host_cid)
            log.debug(f"Sending single divert request slot={product.slot} name={product.name} cid={cid}")
            _divert_single_es_key(self._transport, product, event.target_host_cid)

    def _add_product(self, slot: int) -> None:
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
                entry = ProductEntry(
                    self._transport,
                    slot,
                    product.change_host_feat_idx,
                    product.divert_feat_idx,
                    role,
                    name,
                )
                self._registry.register((self._hid_device_info.path, slot), entry)
        except RuntimeError as e:
            log.debug("Error occurred during adding new product: %s", e)
            if slot in self._products:
                self._products.pop(slot)

    def _cleanup(self) -> None:
        for product in self._products.values():
            if product.divert_feat_idx is not None:
                _undivert_all_es_keys(self._transport, product)
        for slot in self._products:
            self._registry.unregister((self._hid_device_info.path, slot))
        super()._cleanup()


# ── BT listener ──────────────────────────────────────────────────────────────


class BTListener(BaseListener):
    """Handles a single Bluetooth-connected Logitech device."""

    def _init_transport(self) -> None:
        try:
            self._transport = HIDTransport(self._hid_device_info.path, "bluetooth", self._hid_device_info.pid)
        except OSError as e:
            log.debug("Cannot open BT device 0x%04X: %s", self._hid_device_info.pid, e)

    def _detect_products(self) -> None:
        try:
            info = _query_device_info(self._transport, DEVICE_RECEIVER)
            if not info:
                return
            role, name = info
            product = _make_logi_product(self._transport, DEVICE_RECEIVER, role=role, name=name)
            if product:
                self._products[DEVICE_RECEIVER] = product
                self._registry.register(
                    self._hid_device_info.pid,
                    ProductEntry(
                        self._transport,
                        DEVICE_RECEIVER,
                        product.change_host_feat_idx,
                        product.divert_feat_idx,
                        role,
                        name,
                    ),
                )
                if product.divert_feat_idx is not None:
                    _divert_all_es_keys(self._transport, product)
        except RuntimeError as e:
            log.debug("Error probing BT device 0x%04X: %s", self._hid_device_info.pid, e)

    def _handle_event(self, event: BaseEvent) -> None:
        if isinstance(event, HostChangeEvent):
            self._handle_host_change(event)
        elif isinstance(event, ExternalUndivertEvent):
            product = self._products.get(event.slot)
            if product and product.divert_feat_idx is not None:
                _divert_single_es_key(self._transport, product, event.target_host_cid)

    def _cleanup(self) -> None:
        for product in self._products.values():
            if product.divert_feat_idx is not None:
                _undivert_all_es_keys(self._transport, product)
        self._registry.unregister(self._hid_device_info.pid)
        super()._cleanup()


# ── Message parsing ──────────────────────────────────────────────────────────


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


# ── Helpers ──────────────────────────────────────────────────────────────────


def _divert_all_es_keys(transport: HIDTransport, product: LogiProduct) -> None:
    for cid in HOST_SWITCH_CIDS:
        _divert_single_es_key(transport, product, cid)


def _divert_single_es_key(transport: HIDTransport, product: LogiProduct, cid: int) -> None:
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
