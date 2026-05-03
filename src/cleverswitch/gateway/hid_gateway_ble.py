import asyncio
import logging
import threading
import time
from threading import Thread

from .hid_gateway import HidGateway
from .hid_gateway_bt import HidGatewayBT

log = logging.getLogger(__name__)

LOGI_HIDPP_SERVICE = "00010000-0000-1000-8000-011f2000046d"
LOGI_HIDPP_CHAR = "00010001-0000-1000-8000-011f2000046d"
PNP_ID_CHAR = "00002a50-0000-1000-8000-00805f9b34fb"
BLE_PREPEND = bytes([0x11, 0xFF])

try:
    from bleak import BleakClient
    from bleak.backends.corebluetooth.CentralManagerDelegate import CentralManagerDelegate
    from bleak.backends.device import BLEDevice
    from CoreBluetooth import CBUUID
    from Foundation import NSUUID

    _BLE_OK = True
except ImportError:
    BleakClient = None  # type: ignore[assignment,misc]
    CentralManagerDelegate = None  # type: ignore[assignment,misc]
    BLEDevice = None  # type: ignore[assignment,misc]
    CBUUID = None  # type: ignore[assignment,misc]
    NSUUID = None  # type: ignore[assignment,misc]
    _BLE_OK = False


class HidGatewayBLE(HidGatewayBT):
    """macOS-only subclass of HidGatewayBT that replaces the HID read loop with BLE GATT notifications.

    HID writes still go through the inherited transport (confirmed to work under Logi Options+).
    Inbound HID++ notifications arrive via a Logitech proprietary GATT characteristic, which is
    unaffected by LO+'s 33 writes/sec BLE saturation that starves the HID read path.
    """

    def __init__(self, device_info, event_listener) -> None:
        super().__init__(device_info, event_listener)
        self._stop = threading.Event()
        self._ble_client: BleakClient | None = None
        self._ble_loop: asyncio.AbstractEventLoop | None = None
        self._ble_subscribed = threading.Event()

    def _set_connected(self, state: bool) -> None:
        if not state:
            self._ble_subscribed.clear()
            super()._set_connected(False)
            return
        # Set _connected first so the BLE thread can proceed with subscribe.
        # Bypass HidGatewayBT to defer firing the 0x41 connect event until BLE is ready.
        HidGateway._set_connected(self, True)
        if not _BLE_OK:
            self._event_listener.listen(self._create_connection_event())
            return
        while not self._stop.is_set():
            if self._ble_subscribed.wait(timeout=1.0):
                self._event_listener.listen(self._create_connection_event())
                return

    def run(self) -> None:
        if not _BLE_OK:
            log.warning(f"bleak unavailable — pid=0x{self._device_info.pid:04X} BLE notify path disabled")
        else:
            Thread(target=self._run_ble_loop, daemon=True).start()

        while not self._stop.is_set():
            if not self._connected:
                self._try_connect()
            else:
                time.sleep(0.5)

    def close(self) -> None:
        self._stop.set()
        super().close()

    def _run_ble_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._ble_loop = loop
        try:
            loop.run_until_complete(self._ble_main())
        finally:
            self._ble_loop = None
            loop.close()

    async def _ble_main(self) -> None:
        while not self._stop.is_set():
            if not self._connected:
                await asyncio.sleep(0.5)
                continue
            try:
                ble_device = await self._find_peripheral_by_wpid(self._device_info.pid)
                if ble_device is None:
                    await asyncio.sleep(2.0)
                    continue
                await self._connect_and_listen(ble_device)
            except Exception as e:
                log.warning(f"BLE notify error pid=0x{self._device_info.pid:04X}: {e}")
                await asyncio.sleep(2.0)

    async def _connect_and_listen(self, ble_device) -> None:
        def disconnected_callback(_client) -> None:
            log.debug(f"BLE notify dropped pid=0x{self._device_info.pid:04X}")
            self._ble_client = None
            # _set_connected (not direct assignment) fires the inherited HidGatewayBT
            # path that synthesizes the 0x41 disconnect event via _create_connection_event,
            # which downstream subscribers rely on to react to the drop.
            self._set_connected(False)

        async with BleakClient(ble_device, disconnected_callback=disconnected_callback) as client:
            await client.start_notify(LOGI_HIDPP_CHAR, self._on_notify)
            self._ble_client = client
            self._ble_subscribed.set()
            log.debug(f"BLE notify subscribed pid=0x{self._device_info.pid:04X}")
            try:
                while self._connected and not self._stop.is_set():
                    await asyncio.sleep(0.5)
            finally:
                self._ble_client = None

    def _on_notify(self, _sender, data: bytearray) -> None:
        self._event_listener.listen(BLE_PREPEND + bytes(data))

    def _do_write(self, msg: bytes) -> None:
        # Per the HID++ BLE transport, function-call responses come back on the
        # same channel as the request. Send via GATT so responses arrive on our
        # notify subscription instead of the LO+-starved HID input report.
        client = self._ble_client
        loop = self._ble_loop
        if client is not None and loop is not None:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    client.write_gatt_char(LOGI_HIDPP_CHAR, msg[2:], response=False),
                    loop,
                )
                future.result(timeout=2.0)
                return
            except Exception as e:
                log.debug(f"BLE write failed pid=0x{self._device_info.pid:04X}, falling back to HID: {e}")
        super()._do_write(msg)

    async def _find_peripheral_by_wpid(self, target_wpid: int):
        delegate = CentralManagerDelegate()
        await delegate.wait_until_ready()
        candidates = (
            delegate.central_manager.retrieveConnectedPeripheralsWithServices_(
                [CBUUID.UUIDWithString_(LOGI_HIDPP_SERVICE)]
            )
            or []
        )
        for cb in candidates:
            ble_device = BLEDevice(cb.identifier().UUIDString(), cb.name() or "unknown", (cb, delegate))
            try:
                async with BleakClient(ble_device) as probe:
                    pnp = await probe.read_gatt_char(PNP_ID_CHAR)
                    if int.from_bytes(pnp[3:5], "little") == target_wpid:
                        return ble_device
            except Exception as e:
                log.debug(f"PnP probe failed for {ble_device.address}: {e}")
        return None
