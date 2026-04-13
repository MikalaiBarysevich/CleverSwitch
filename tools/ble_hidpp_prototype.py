#!/usr/bin/env python3
"""
Prototype: Subscribe to Logitech HID++ GATT notifications via CoreBluetooth (bleak).

Purpose: Test whether GATT-level notification subscription receives HID++ events
reliably when Logitech Options+ is running — bypassing hidapi/IOHIDManager/BTLEServer.

Usage:
    pip install bleak pyobjc-framework-CoreBluetooth
    python tools/ble_hidpp_prototype.py                    # list connected Logitech devices + scan
    python tools/ble_hidpp_prototype.py --name "MX Keys"   # connect to specific device by name
    python tools/ble_hidpp_prototype.py --address <UUID>    # connect by CoreBluetooth UUID

Press ES (Easy-Switch) keys while this runs. Compare notification delivery
with CS running via hidapi on the same device.
"""

import argparse
import asyncio
import logging
import platform
import struct
import sys
import time

from bleak import BleakClient, BleakScanner, BLEDevice

log = logging.getLogger("ble_hidpp")

# Logitech GATT UUIDs
LOGI_HIDPP_SERVICE = "00010000-0000-1000-8000-011f2000046d"
LOGI_HIDPP_CHAR = "00010001-0000-1000-8000-011f2000046d"

# Logitech USB VID for BLE scan filtering
LOGI_COMPANY_ID = 0x046D

# HID++ constants
DEV_IDX_BLE = 0xFF
ROOT_FEATURE_INDEX = 0x00

# Easy-Switch CIDs
HOST_SWITCH_CIDS = {0x00D1: 1, 0x00D2: 2, 0x00D3: 3}

# Feature codes
FEAT_REPROG_CONTROLS_V4 = 0x1B04
FEAT_CHANGE_HOST = 0x1814


def format_hidpp(data: bytes) -> str:
    """Format HID++ GATT payload for logging."""
    hex_str = data.hex(" ")
    if len(data) < 3:
        return f"[{len(data)}B] {hex_str}"

    dev_idx = data[0]
    feat_idx = data[1]
    fn = (data[2] >> 4) & 0x0F
    sw_id = data[2] & 0x0F

    info = f"dev=0x{dev_idx:02X} feat_idx={feat_idx} fn={fn} sw_id={sw_id}"

    if sw_id == 0:
        info += " [NOTIFICATION]"

    return f"[{len(data)}B] {info} | {hex_str}"


class HidppBlePrototype:
    def __init__(self):
        self.client: BleakClient | None = None
        self.notification_count = 0
        self.response_count = 0
        self.feature_map: dict[int, int] = {}  # feature_code -> feature_index
        self.start_time = time.monotonic()

    def on_notification(self, sender, data: bytearray):
        """Called for every GATT notification on the HID++ characteristic."""
        elapsed = time.monotonic() - self.start_time
        sw_id = data[2] & 0x0F if len(data) >= 3 else -1

        if sw_id == 0:
            self.notification_count += 1
            label = "NOTIF"
        else:
            self.response_count += 1
            label = "RESP "

        log.info(
            "[%7.3fs] #%d %s %s",
            elapsed,
            self.notification_count + self.response_count,
            label,
            format_hidpp(bytes(data)),
        )

    async def send_request(self, feat_idx: int, fn: int, sw_id: int, *params: int) -> None:
        """Send an HID++ request via GATT write."""
        payload = bytearray(19)
        payload[0] = DEV_IDX_BLE
        payload[1] = feat_idx
        payload[2] = (fn << 4) | (sw_id & 0x0F)
        for i, p in enumerate(params):
            if i + 3 < len(payload):
                payload[i + 3] = p

        log.info("SEND >> %s", format_hidpp(bytes(payload)))
        await self.client.write_gatt_char(LOGI_HIDPP_CHAR, payload, response=True)

    async def ping(self) -> bool:
        """Send HID++ 2.0 ping (IRoot.getProtocolVersion)."""
        log.info("--- Sending ping ---")
        await self.send_request(ROOT_FEATURE_INDEX, 1, 0x0F, 0, 0, 0xAA)
        await asyncio.sleep(0.5)
        return True

    async def get_feature_index(self, feature_code: int) -> int | None:
        """IRoot.getFeatureID (fn=0) to resolve feature code -> index."""
        hi = (feature_code >> 8) & 0xFF
        lo = feature_code & 0xFF
        await self.send_request(ROOT_FEATURE_INDEX, 0, 0x0F, hi, lo)
        await asyncio.sleep(0.3)
        # Response will arrive via on_notification; manual for prototype
        return None

    async def run(self, device_address: str):
        """Connect, subscribe, and listen for HID++ events."""
        log.info("Connecting to %s ...", device_address)

        # Let Bleak handle the CoreBluetooth lookup by UUID
        device = await BleakScanner.find_device_by_address(device_address, timeout=5.0)

        if not device:
            log.error(f"Could not find device with address {device_address}")
            return

        async with BleakClient(device) as client:
            self.client = client
            log.info("Connected: %s", client.is_connected)

            # List services to find Logitech HID++ characteristic
            for service in client.services:
                if LOGI_HIDPP_SERVICE in service.uuid.lower():
                    log.info("Found Logitech HID++ service: %s", service.uuid)
                    for char in service.characteristics:
                        log.info(
                            "  Characteristic: %s  props=%s  handle=0x%04X",
                            char.uuid, char.properties, char.handle,
                        )

            # Subscribe to notifications
            log.info("Subscribing to HID++ notifications on %s ...", LOGI_HIDPP_CHAR)
            await client.start_notify(LOGI_HIDPP_CHAR, self.on_notification)
            log.info("Subscribed. Listening for HID++ events.")

            # Send ping to verify communication
            await self.ping()

            # Resolve feature 0x1B04 (REPROG_CONTROLS_V4)
            log.info("--- Querying feature 0x1B04 (REPROG_CONTROLS_V4) ---")
            await self.get_feature_index(FEAT_REPROG_CONTROLS_V4)

            # Resolve feature 0x1814 (CHANGE_HOST)
            log.info("--- Querying feature 0x1814 (CHANGE_HOST) ---")
            await self.get_feature_index(FEAT_CHANGE_HOST)

            log.info("")
            log.info("=" * 60)
            log.info("  READY — press Easy-Switch keys on the device now!")
            log.info("  Ctrl+C to stop.")
            log.info("=" * 60)
            log.info("")

            # Keep listening
            try:
                while True:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                pass

            await client.stop_notify(LOGI_HIDPP_CHAR)

        log.info(
            "Done. Received %d notifications, %d responses.",
            self.notification_count, self.response_count,
        )


def _get_connected_peripheral(address: str):
    """Use CoreBluetooth to retrieve an already-connected peripheral by UUID.

    Returns a CBPeripheral object that BleakClient can use directly,
    or None if not found. macOS only.
    """
    try:
        from CoreBluetooth import CBCentralManager, CBUUID
        from Foundation import NSUUID
        import objc
        import time as _time
    except ImportError:
        log.warning("pyobjc-framework-CoreBluetooth not installed. Run: pip install pyobjc-framework-CoreBluetooth")
        return None

    # CBCentralManager needs a run loop tick to initialize
    manager = CBCentralManager.alloc().initWithDelegate_queue_(None, None)

    # Wait for CBCentralManager to be ready (state == .poweredOn == 5)
    deadline = _time.monotonic() + 3.0
    while manager.state() != 5 and _time.monotonic() < deadline:
        from Foundation import NSRunLoop, NSDate
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.1))

    if manager.state() != 5:
        log.warning("CoreBluetooth not powered on (state=%d)", manager.state())
        return None

    # Try retrieveConnectedPeripherals with the Logitech HID++ service UUID
    logi_service = CBUUID.UUIDWithString_(LOGI_HIDPP_SERVICE)
    connected = manager.retrieveConnectedPeripheralsWithServices_([logi_service])

    if connected:
        log.info("Found %d connected peripheral(s) with Logitech HID++ service:", len(connected))
        for p in connected:
            log.info("  %s — %s", p.identifier().UUIDString(), p.name() or "unnamed")
            if p.identifier().UUIDString().upper() == address.upper():
                return p

    # Also try retrievePeripherals by known UUID
    ns_uuid = NSUUID.alloc().initWithUUIDString_(address)
    if ns_uuid:
        known = manager.retrievePeripheralsWithIdentifiers_([ns_uuid])
        if known and len(known) > 0:
            log.info("Found peripheral by UUID: %s", known[0].name() or "unnamed")
            return known[0]

    log.info("Peripheral %s not found via CoreBluetooth", address)
    return None


def _list_connected_logitech():
    """List all connected peripherals advertising the Logitech HID++ service. macOS only."""
    try:
        from CoreBluetooth import CBCentralManager, CBUUID
        import time as _time
    except ImportError:
        return []

    manager = CBCentralManager.alloc().initWithDelegate_queue_(None, None)
    deadline = _time.monotonic() + 3.0
    while manager.state() != 5 and _time.monotonic() < deadline:
        from Foundation import NSRunLoop, NSDate
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.1))

    if manager.state() != 5:
        return []

    logi_service = CBUUID.UUIDWithString_(LOGI_HIDPP_SERVICE)
    connected = manager.retrieveConnectedPeripheralsWithServices_([logi_service])

    results = []
    for p in connected or []:
        results.append((p.identifier().UUIDString(), p.name() or "unnamed"))
    return results


async def scan_for_logitech(name_filter: str | None = None, timeout: float = 10.0):
    """Scan for Logitech BLE devices.

    Note: On macOS, already-paired/connected BLE devices do NOT advertise,
    so they won't appear in scan results. Use --address with the CoreBluetooth
    UUID instead (find it in Bluetooth system log or System Information).
    """
    log.info("Scanning for Logitech BLE devices (%0.0fs)...", timeout)
    log.info("NOTE: Already-connected devices won't appear in scan on macOS.")
    log.info("Use --address <CoreBluetooth-UUID> to connect to a paired device directly.")

    devices = await BleakScanner.discover(timeout=timeout, return_adv=True)

    logitech_devices = []
    for d, adv in devices.values():
        is_logi = False

        # Check by name
        if d.name and "logi" in d.name.lower():
            is_logi = True
        if d.name and any(kw in d.name.lower() for kw in ["mx ", "ergo", "craft", "pop", "k380", "k780", "m720"]):
            is_logi = True

        # Check by manufacturer data (company ID 0x046D)
        if adv.manufacturer_data and LOGI_COMPANY_ID in adv.manufacturer_data:
            is_logi = True

        # Check by Logitech HID++ service UUID
        if LOGI_HIDPP_SERVICE in [u.lower() for u in adv.service_uuids]:
            is_logi = True

        if is_logi:
            if name_filter and name_filter.lower() not in (d.name or "").lower():
                continue
            logitech_devices.append(d)
            log.info("  Found: %s (%s) RSSI=%s", d.name, d.address, adv.rssi)

    return logitech_devices


async def main():
    parser = argparse.ArgumentParser(
        description="Logitech HID++ BLE GATT prototype",
        epilog=(
            "On macOS, use the CoreBluetooth UUID as --address (not MAC).\n"
            "Find it via: sudo log stream --predicate 'subsystem == \"com.apple.bluetooth\"' --level debug\n"
            "Look for CBDevice lines with VID 0x046D, e.g.:\n"
            "  CBDevice B9840933-D989-39F7-57CE-792EFCA7D70C ... modU MX Keys\n"
            "Then run: python tools/ble_hidpp_prototype.py --address B9840933-D989-39F7-57CE-792EFCA7D70C"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--address", help="BLE device address (CoreBluetooth UUID on macOS)")
    parser.add_argument("--name", help="Filter scanned devices by name (e.g., 'MX Keys')")
    parser.add_argument("--scan-timeout", type=float, default=10.0, help="BLE scan timeout in seconds")
    args = parser.parse_args()

    proto = HidppBlePrototype()

    if args.address:
        await proto.run(args.address)
    else:
        # On macOS, try listing already-connected Logitech devices first
        connected = []
        if platform.system() == "Darwin":
            connected = _list_connected_logitech()
            if connected:
                log.info("Connected Logitech BLE devices (via CoreBluetooth):")
                for uuid, name in connected:
                    log.info("  %s — %s", uuid, name)

                # Filter by name if provided
                if args.name:
                    connected = [(u, n) for u, n in connected if args.name.lower() in n.lower()]

                if len(connected) == 1:
                    log.info("Connecting to: %s (%s)", connected[0][1], connected[0][0])
                    await proto.run(connected[0][0])
                    return
                elif len(connected) > 1:
                    log.info("\nMultiple connected devices. Select one:")
                    for i, (uuid, name) in enumerate(connected):
                        log.info("  [%d] %s (%s)", i, name, uuid)
                    choice = int(input("Enter number: "))
                    await proto.run(connected[choice][0])
                    return

        # Fall back to BLE scan for advertising devices
        devices = await scan_for_logitech(name_filter=args.name, timeout=args.scan_timeout)
        if not devices:
            log.error("No Logitech BLE devices found.")
            if not connected:
                log.error("No connected devices found either. Is the device awake and paired?")
            sys.exit(1)

        if len(devices) == 1:
            target = devices[0]
        else:
            log.info("\nMultiple devices found. Select one:")
            for i, d in enumerate(devices):
                log.info("  [%d] %s (%s)", i, d.name, d.address)
            choice = int(input("Enter number: "))
            target = devices[choice]

        log.info("Selected: %s (%s)", target.name, target.address)
        await proto.run(target.address)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("\nStopped by user.")
