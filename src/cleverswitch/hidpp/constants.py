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

# The HID++ interface on receivers is always interface 2
HID_INTERFACE = 2
# On Windows/macOS interface numbers are unreliable; filter by usage_page instead
HIDPP_USAGE_PAGE = 0xFF00

# Known device wireless PIDs (when paired to a receiver)
MX_KEYS_WPID = 0x408A
MX_MASTER_3_WPID = 0x4082

# Known device Bluetooth product IDs (when connected directly via BT)
MX_KEYS_BTID = 0xB35B
MX_MASTER_3_BTID = 0xB023

# All Logitech Bluetooth product IDs we care about
BT_PRODUCT_IDS = (MX_KEYS_BTID, MX_MASTER_3_BTID)

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
FEATURE_CHANGE_HOST = 0x1814
FEATURE_HOSTS_INFO = 0x1815
FEATURE_REPROG_CONTROLS_V4 = 0x1B04  # Reprogrammable keys / button diversion

# Host-Switch Channel CID codes → 0-based host index
HOST_SWITCH_CIDS = {0x00D1: 0, 0x00D2: 1, 0x00D3: 2}

# REPROG_CONTROLS_V4 key capability flag (byte 4 of getCidInfo response)
KEY_FLAG_DIVERTABLE = 0x20  # key can be temporarily diverted

# Mapping flag bit for setCidReporting (byte 2 of request payload)
MAP_FLAG_DIVERTED = 0x01  # temporarily divert (cleared on device reset)
MAP_FLAG_PERSISTENTLY_DIVERTED = 0x04  # persistently divert (cleared on device reset)

# CHANGE_HOST function codes (upper nibble of the function/address byte)
CHANGE_HOST_FN_GET = 0x00  # GetHostCount — returns (num_hosts, current_host)
CHANGE_HOST_FN_SET = 0x10  # SetCurrentHost — switches to target; no reply

# ── HID++ 1.0 register access ─────────────────────────────────────────────────

# Register read request_id: 0x8100 | (register & 0x2FF)
# For register 0x2B5 (RECEIVER_INFO): request_id = 0x83B5
REG_RECEIVER_INFO = 0x2B5

# Sub-register offsets within RECEIVER_INFO
REG_PAIRING_INFO_UNIFYING = 0x20  # 0x20 + (slot - 1),  slots 1-6
REG_PAIRING_INFO_BOLT = 0x50  # 0x50 + slot,         slots 1-6

# ── DJ notification sub-IDs ───────────────────────────────────────────────────

DJ_DEVICE_UNPAIRING = 0x40
DJ_DEVICE_PAIRING = 0x41  # connection status notification (REPORT_DJ or REPORT_SHORT)
DJ_HOST_CHANGE = 0x42  # device switched host; address = 0-based target host index

# Flags byte (data[0]) of a DJ_DEVICE_PAIRING notification
DJ_FLAG_DISCONNECTED = 0x40  # bit 6: 1 = disconnected (link not established)
DJ_FLAG_ENCRYPTED = 0x20  # bit 5: 1 = link encrypted
DJ_PROTO_BOLT = 0x10  # address byte value that indicates Bolt protocol
