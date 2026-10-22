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

# bleak's disconnect awaits a CoreBluetooth confirmation that never arrives when Bluetooth is
# powered off mid-session; without a bound the channel's loop hangs and never reconnects.
_DISCONNECT_TIMEOUT = 5.0

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

    The channel runs only while activated. It reports through `on_state` when its subscription
    comes up, and when it drops on its own while still active. It never changes anyone else's
    state: a GATT drop is not a device drop.
    """

    def __init__(
        self,
        pid: int,
        on_report: Callable[[bytes], None],
        on_state: Callable[[bool], None],
        stop: threading.Event,
    ) -> None:
        self._pid = pid
        self._on_report = on_report
        self._on_state = on_state
        self._stop = stop
        self._active = threading.Event()
        self._client: BleakClient | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        # Created on the channel's own loop and reused; a new one per lookup leaks a CBCentralManager.
        self._delegate: CentralManagerDelegate | None = None
        # CoreBluetooth identifier of the peripheral that matched our pid, so reconnects skip probing.
        self._peripheral_id: str | None = None
        self.subscribed = threading.Event()

    def start(self) -> None:
        Thread(target=self._run_loop, daemon=True).start()

    def activate(self) -> None:
        self._active.set()

    def deactivate(self) -> None:
        self._active.clear()

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
        reported_missing = False
        while not self._stop.is_set():
            if not self._active.is_set():
                reported_missing = False
                await asyncio.sleep(0.5)
                continue
            try:
                ble_device = await self._find_peripheral_by_wpid(self._pid)
                if ble_device is None:
                    if not reported_missing:
                        log.debug(f"No GATT peripheral for pid=0x{self._pid:04X} yet, retrying")
                        reported_missing = True
                    await asyncio.sleep(2.0)
                    continue
                reported_missing = False
                await self._connect_and_listen(ble_device)
            except Exception as e:
                log.warning(f"BLE notify error pid=0x{self._pid:04X}: {e}")
                await asyncio.sleep(2.0)

    async def _connect_and_listen(self, ble_device) -> None:
        dropped = threading.Event()

        def disconnected_callback(_client) -> None:
            log.debug(f"BLE notify dropped pid=0x{self._pid:04X}")
            dropped.set()

        client = BleakClient(ble_device, disconnected_callback=disconnected_callback)
        await client.connect()
        try:
            await client.start_notify(LOGI_HIDPP_CHAR, self._on_notify)
            self._client = client
            self.subscribed.set()
            log.debug(f"BLE notify subscribed pid=0x{self._pid:04X}")
            self._on_state(True)
            # is_connected is checked too: the drop callback does not fire when Bluetooth is
            # powered off mid-session.
            while self._active.is_set() and not self._stop.is_set() and not dropped.is_set() and client.is_connected:
                await asyncio.sleep(0.5)
        finally:
            was_up = self.subscribed.is_set()
            self._client = None
            self.subscribed.clear()
            # Only a drop on its own is news. Ending because HID went away or we are shutting down
            # must stay silent: a re-arm then would re-divert keys that shutdown just un-diverted.
            if was_up and self._active.is_set() and not self._stop.is_set():
                self._on_state(False)
            # No explicit stop_notify: disconnecting tears the subscription down anyway, and
            # calling it throws on a remote drop.
            await self._disconnect(client)

    async def _disconnect(self, client) -> None:
        try:
            await asyncio.wait_for(client.disconnect(), _DISCONNECT_TIMEOUT)
        except Exception as e:
            log.debug(f"BLE disconnect did not complete for pid=0x{self._pid:04X}: {e!r}")

    def _on_notify(self, _sender, data: bytearray) -> None:
        raw = BLE_PREPEND + bytes(data)
        log.debug(f"Received BLE event from pid=0x{self._pid:04X}: {raw.hex()}")
        self._on_report(raw)

    async def _find_peripheral_by_wpid(self, target_wpid: int):
        if self._delegate is None:
            self._delegate = CentralManagerDelegate()
        delegate = self._delegate
        await delegate.wait_until_ready()
        candidates = (
            delegate.central_manager.retrieveConnectedPeripheralsWithServices_(
                [CBUUID.UUIDWithString_(LOGI_HIDPP_SERVICE)]
            )
            or []
        )
        devices = [BLEDevice(cb.identifier().UUIDString(), cb.name() or "unknown", (cb, delegate)) for cb in candidates]
        for ble_device in devices:
            if ble_device.address == self._peripheral_id:
                return ble_device
        for ble_device in devices:
            if await self._probe_wpid(ble_device) == target_wpid:
                self._peripheral_id = ble_device.address
                return ble_device
        return None

    async def _probe_wpid(self, ble_device) -> int | None:
        probe = BleakClient(ble_device)
        try:
            await probe.connect()
            pnp = await probe.read_gatt_char(PNP_ID_CHAR)
            return int.from_bytes(pnp[3:5], "little")
        except Exception as e:
            log.debug(f"PnP probe failed for {ble_device.address}: {e}")
            return None
        finally:
            await self._disconnect(probe)
