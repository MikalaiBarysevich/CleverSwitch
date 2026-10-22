import asyncio
import logging
import threading
from collections.abc import Callable
from threading import Thread

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


class GattChannel:
    """macOS HID++ channel over the Logitech proprietary GATT characteristic.

    Its asyncio thread is the only owner of the BleakClient. Inbound notifications are turned into
    20-byte HID++ long reports and handed to `on_report`; outbound writes are marshalled onto that
    thread by `write()`.

    The channel runs only while `link_up` is set, and reports a GATT drop through `on_drop`.
    """

    def __init__(
        self,
        pid: int,
        on_report: Callable[[bytes], None],
        link_up: threading.Event,
        on_drop: Callable[[], None],
        stop: threading.Event,
    ) -> None:
        self._pid = pid
        self._on_report = on_report
        self._link_up = link_up
        self._on_drop = on_drop
        self._stop = stop
        self._client: BleakClient | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.subscribed = threading.Event()

    def start(self) -> None:
        Thread(target=self._run_loop, daemon=True).start()

    def write(self, msg: bytes, timeout: float = 2.0) -> bool:
        # Per the HID++ BLE transport, function-call responses come back on the same channel as
        # the request, so writing via GATT keeps our own responses on the notify subscription.
        #
        # response=True (ATT Write Request) is required, not an optimisation. bleak never checks
        # canSendWriteWithoutResponse, so a write-*without*-response is silently discarded whenever
        # the OS has no credit — only 1 of 3 setCidReporting requests was landing. The with-response
        # path awaits the ATT confirmation, which acknowledges every write and serialises the burst.
        client = self._client
        loop = self._loop
        if client is None or loop is None:
            log.debug(f"BLE client not ready for pid=0x{self._pid:04X}, writing via HID instead")
            return False
        try:
            future = asyncio.run_coroutine_threadsafe(
                client.write_gatt_char(LOGI_HIDPP_CHAR, msg[2:], response=True),
                loop,
            )
            future.result(timeout=timeout)
        except Exception as e:
            log.debug(f"BLE write failed pid=0x{self._pid:04X}, falling back to HID: {e}")
            return False
        log.debug(f"Wrote via GATT to pid=0x{self._pid:04X}")
        return True

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._main())
        finally:
            self._loop = None
            loop.close()

    async def _main(self) -> None:
        while not self._stop.is_set():
            if not self._link_up.is_set():
                await asyncio.sleep(0.5)
                continue
            try:
                ble_device = await self._find_peripheral_by_wpid(self._pid)
                if ble_device is None:
                    await asyncio.sleep(2.0)
                    continue
                await self._connect_and_listen(ble_device)
            except Exception as e:
                log.warning(f"BLE notify error pid=0x{self._pid:04X}: {e}")
                await asyncio.sleep(2.0)

    async def _connect_and_listen(self, ble_device) -> None:
        def disconnected_callback(_client) -> None:
            log.debug(f"BLE notify dropped pid=0x{self._pid:04X}")
            self._client = None
            self._on_drop()

        async with BleakClient(ble_device, disconnected_callback=disconnected_callback) as client:
            await client.start_notify(LOGI_HIDPP_CHAR, self._on_notify)
            self._client = client
            self.subscribed.set()
            log.debug(f"BLE notify subscribed pid=0x{self._pid:04X}")
            try:
                while self._link_up.is_set() and not self._stop.is_set():
                    await asyncio.sleep(0.5)
            finally:
                # No explicit stop_notify: leaving the `async with` disconnects the client, which
                # tears the subscription down anyway. Calling it here throws on a remote drop.
                self._client = None

    def _on_notify(self, _sender, data: bytearray) -> None:
        raw = BLE_PREPEND + bytes(data)
        log.debug(f"Received BLE event from pid=0x{self._pid:04X}: {raw.hex()}")
        self._on_report(raw)

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
