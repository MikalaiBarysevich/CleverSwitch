# Windows HID Collection Strategy for Unifying/Bolt Receivers

## Background
On Windows, each HID Application Collection is a separate logical device with its own path.
The OS routes incoming input reports to the handle whose report descriptor declares that report ID.
A handle for usage=0x0001 (short, report 0x10) will NOT receive report 0x11 data.

## Receiver collection layout (legacy scheme, usage_page 0xFF00)
Applies to Unifying 0xC52B and Bolt 0xC548:

| usage  | Report ID | Size    | Direction    | Purpose                        |
|--------|-----------|---------|--------------|--------------------------------|
| 0x0001 | 0x10      | 7 bytes | In + Out     | Short HID++ requests/responses |
| 0x0002 | 0x11      | 20 bytes| In + Out     | Long HID++ requests/responses  |
| 0x0004 | 0x20      | varies  | In only      | DJ device connect/disconnect   |

## Operation → collection mapping

| Operation                            | Write to    | Read from   |
|--------------------------------------|-------------|-------------|
| HID++ 2.0 short request (0x10)       | 0x0001      | 0x0002 (*)  |
| HID++ 2.0 long request (0x11)        | 0x0002      | 0x0002      |
| HID++ 1.0 short register (0x81)      | 0x0001      | 0x0001      |
| HID++ 1.0 long register GET (0x83)   | 0x0001      | 0x0002      |
| DJ device arrival/removal (0x20)     | —           | 0x0004      |

(*) HID++ 2.0 responses are ALWAYS long 0x11 regardless of request size.

## Recommended implementation on Windows
Open only the long collection (usage=0x0002) for HID++ 2.0 communication:
- Pad all requests to 20 bytes and send as report 0x11 (long format)
- All HID++ 2.0 responses come back as 0x11 on this same handle
- Open the DJ collection (usage=0x0004) separately for device-arrival events
- No need to open the short collection at all for HID++ 2.0 operation

## Source
Transaction log in logitech_hidpp_2.0_specification_draft_2012-06-04.pdf (pages 15-16),
and collection usage table in logitech_hidpp_hid_vendor_collection_usages.pdf.
