#!/usr/bin/env python3
"""
Prototype: Subscribe to Logitech HID++ GATT notifications via CoreBluetooth (bleak).

Purpose: Test whether GATT-level notification subscription receives HID++ events
reliably when Logitech Options+ is running — bypassing hidapi/IOHIDManager/BTLEServer.

Usage:
    pip install bleak
    python tools/ble_hidpp_prototype.py                    # scan + connect to first Logitech device
    python tools/ble_hidpp_prototype.py --name "MX Keys"   # connect to specific device
    python tools/ble_hidpp_prototype.py --address XX:XX:XX  # connect by BLE address

Press ES (Easy-Switch) keys while this runs. Compare notification delivery
with CS running via hidapi on the same device.
"""

import argparse
import asyncio
import logging
import struct
import sys
import time

from bleak import BleakClient, BleakScanner

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

        async with BleakClient(device_address) as client:
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


async def scan_for_logitech(name_filter: str | None = None, timeout: float = 10.0):
    """Scan for Logitech BLE devices."""
    log.info("Scanning for Logitech BLE devices (%0.0fs)...", timeout)

    devices = await BleakScanner.discover(timeout=timeout)

    logitech_devices = []
    for d in devices:
        is_logi = False

        # Check by name
        if d.name and "logi" in d.name.lower():
            is_logi = True
        if d.name and any(kw in d.name.lower() for kw in ["mx ", "ergo", "craft", "pop", "k380", "k780", "m720"]):
            is_logi = True

        # Check by manufacturer data (company ID 0x046D)
        if d.metadata and "manufacturer_data" in d.metadata:
            if LOGI_COMPANY_ID in d.metadata["manufacturer_data"]:
                is_logi = True

        if is_logi:
            if name_filter and name_filter.lower() not in (d.name or "").lower():
                continue
            logitech_devices.append(d)
            log.info("  Found: %s (%s) RSSI=%s", d.name, d.address, d.rssi)

    return logitech_devices


async def main():
    parser = argparse.ArgumentParser(description="Logitech HID++ BLE GATT prototype")
    parser.add_argument("--address", help="BLE device address to connect to directly")
    parser.add_argument("--name", help="Filter scanned devices by name (e.g., 'MX Keys')")
    parser.add_argument("--scan-timeout", type=float, default=10.0, help="BLE scan timeout in seconds")
    args = parser.parse_args()

    proto = HidppBlePrototype()

    if args.address:
        await proto.run(args.address)
    else:
        devices = await scan_for_logitech(name_filter=args.name, timeout=args.scan_timeout)
        if not devices:
            log.error("No Logitech BLE devices found. Make sure device is awake and in range.")
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
