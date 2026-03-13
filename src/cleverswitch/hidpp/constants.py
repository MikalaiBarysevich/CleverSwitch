"""HID++ protocol constants.

Sources:
  - Solaar codebase (lib/logitech_receiver/)
  - Logitech HID++ 1.0 / 2.0 documentation (https://drive.google.com/file/d/1UGDCuqnKBm7U8a6t6g3QlEZgKeaAzmAx)
"""

# ── Logitech USB identifiers ──────────────────────────────────────────────────

LOGITECH_VENDOR_ID = 0x046D

# Receiver USB product IDs
BOLT_PID = 0xC548
UNIFYING_PIDS = (0xC52B, 0xC532)
ALL_RECEIVER_PIDS = (BOLT_PID,) + UNIFYING_PIDS

HIDPP_USAGE_PAGES = [0xFF00, 0xFF43]  # 0xFF00 = receiver, 0xFF43 = Bluetooth direct
HIDPP_USAGE_SHORT = 0x0001  # Short HID++ (report 0x10, 7 bytes) — Linux/macOS single entry
HIDPP_USAGE_LONG = 0x0002  # Long HID++ (report 0x11, 20 bytes) — Windows long collection
HIDPP_BT_USAGE_LONG = 0x0202  # Long HID++ over Bluetooth
HIDPP_USAGES_LONG = [HIDPP_USAGE_LONG, HIDPP_BT_USAGE_LONG]

# ── HID++ report IDs and message sizes ───────────────────────────────────────

REPORT_SHORT = 0x10  # 7 bytes total
REPORT_LONG = 0x11  # 20 bytes total
REPORT_DJ = 0x20  # 15 bytes total (Unifying/Bolt receiver events)

MSG_SHORT_LEN = 7
MSG_LONG_LEN = 20
MSG_DJ_LEN = 15
MAX_READ_SIZE = 32

# ── Addressing ────────────────────────────────────────────────────────────────

# Device number used when targeting the receiver itself, or a direct (BT/USB) device
DEVICE_RECEIVER = 0xFF

# Software ID — lower nibble of the function byte in requests.
# Always has bit 3 set (>= 0x08) so notifications (sw_id=0) are distinguishable.
SW_ID = 0x08

# ── HID++ 2.0 feature codes ───────────────────────────────────────────────────

FEATURE_ROOT = 0x0000  # Look up feature index by code; also used for ping
FEATURE_DEVICE_TYPE_AND_NAME = 0x0005  # x0005: getDeviceType(), getDeviceName()
FEATURE_CHANGE_HOST = 0x1814
FEATURE_REPROG_CONTROLS_V4 = 0x1B04  # Reprogrammable keys / button diversion

# x0005 getDeviceType() return values
DEVICE_TYPE_KEYBOARD = 0
DEVICE_TYPE_MOUSE = 3
DEVICE_TYPE_TRACKPAD = 4  # treat as mouse-class
DEVICE_TYPE_TRACKBALL = 5  # treat as mouse-class

# Host-Switch Channel CID codes → 0-based host index
HOST_SWITCH_CIDS = {0x00D1: 0, 0x00D2: 1, 0x00D3: 2}

# REPROG_CONTROLS_V4 key capability flag (byte 4 of getCidInfo response)
KEY_FLAG_DIVERTABLE = 0x20  # key can be temporarily diverted

# Mapping flag bit for setCidReporting (byte 2 of request payload)
MAP_FLAG_DIVERTED = 0x01  # temporarily divert (cleared on device reset)
MAP_FLAG_PERSISTENTLY_DIVERTED = 0x04  # persistently divert (cleared on device reset)

# CHANGE_HOST function codes (upper nibble of the function/address byte)
CHANGE_HOST_FN_SET = 0x10  # SetCurrentHost — switches to target; no reply


HID_DEVICE_PAIRING = 0x41
DJ_DEVICE_PAIRING = 0x42
