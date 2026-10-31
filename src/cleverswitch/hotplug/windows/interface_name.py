import re

from ...hidpp.constants import LOGITECH_VENDOR_ID

# USB: \\?\HID#VID_046D&PID_C52B&MI_02&Col01#...
# BLE: \\?\HID#{00001812-...}_Dev_VID&02046d_PID&b35b_REV&0013_...&Col03#...
# The two digits before a BLE vendor id name its source (01 Bluetooth SIG, 02 USB-IF).
_USB = re.compile(r"#VID_([0-9A-F]{4})&PID_([0-9A-F]{4})", re.IGNORECASE)
_BLE = re.compile(r"_VID&[0-9A-F]{2}([0-9A-F]{4})_PID&([0-9A-F]{4})", re.IGNORECASE)


def hid_interface_pid(symbolic_link: str) -> int | None:
    match = _USB.search(symbolic_link) or _BLE.search(symbolic_link)
    if match is None or int(match.group(1), 16) != LOGITECH_VENDOR_ID:
        return None
    return int(match.group(2), 16)
