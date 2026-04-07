# x1b04 setCidReporting — Byte Layout and bfield Reference

Source: `x1b04_specialkeysmsebuttons_v6.pdf`, Tables 6 and 7, pages 7–10.

## Function identity
- Feature 0x1B04, function index [3]
- Byte 3 of HID++ message = (0x3 << 4) | sw_id = 0x30 | sw_id
  - Solaar uses sw_id=2 → byte3=0x32
  - CleverSwitch uses sw_id=1 → byte3=0x31

## Request packet (Table 6) — long report 0x11, 20 bytes

| Byte | Bits 7-0 | Description |
|------|----------|-------------|
| 0 | — | 0x11 (report ID) |
| 1 | — | device index |
| 2 | — | feature index of 0x1B04 |
| 3 | — | 0x30 \| sw_id |
| 4 | — | cid msb |
| 5 | — | cid lsb |
| 6 | [7]=fvalid [6]=forceRawXY [5]=rvalid [4]=rawXY [3]=pvalid [2]=persist [1]=dvalid [0]=divert | bfield |
| 7 | — | remap msb |
| 8 | — | remap lsb |
| 9 | [4]=wvalid [3]=rawWheel [2]=avalid [1]=analyticsKeyEvt [0]=--- | extra flags |
| 10-19 | — | zero-padded |

## Response (Table 7)
**Echoes the request exactly.** Bytes 0-9 identical to request; bytes 10-15 reserved (zeros).
This means when you observe another SW's setCidReporting on your fd, byte3 has THEIR sw_id,
not an event code. It is NOT an unsolicited event — it is a reflected response.

## Byte 6 (bfield) bit definitions

| Bit | Name | Role | Values |
|-----|------|------|--------|
| 7 | fvalid | mask | 0=ignore forceRawXY, 1=apply forceRawXY |
| 6 | forceRawXY | action | 1=force-divert raw XY without user press |
| 5 | rvalid | mask | 0=ignore rawXY, 1=apply rawXY |
| 4 | rawXY | action | 1=divert raw mouse XY reports |
| 3 | pvalid | mask | 0=ignore persist, 1=apply persist |
| 2 | persist | action | 1=persistently divert (survives HID++ reset) |
| 1 | dvalid | mask | 0=ignore divert, 1=apply divert |
| 0 | divert | action | 1=temporarily divert |

Rule: device only updates a setting when the matching *valid bit is 1.
If either divert=1 or persist=1 (with valid bit set), control is diverted via HID++ notification.

## Byte 9 extra flags

| Bit | Name | Role |
|-----|------|------|
| 4 | wvalid | mask for rawWheel |
| 3 | rawWheel | action: divert raw wheel reports |
| 2 | avalid | mask for analyticsKeyEvt |
| 1 | analyticsKeyEvt | action: enable analytics key events |
| 0 | --- | reserved |

## Common bfield values

| bfield | Binary | Meaning |
|--------|--------|---------|
| 0x0F | 00001111 | dvalid+divert=1, pvalid+persist=1 → FULL DIVERT (temp+persist ON) |
| 0x03 | 00000011 | dvalid=1, divert=1 → temp divert ON only |
| 0x0C | 00001100 | pvalid=1, persist=1 → persist divert ON only |
| 0x22 | 00100010 | dvalid=1 divert=0, rvalid=1 rawXY=0 → clear temp divert and rawXY |
| 0x0A | 00001010 | dvalid=1 divert=0, pvalid=1 persist=0 → clear BOTH temp and persist divert |
| 0x02 | 00000010 | dvalid=1, divert=0 → clear temp divert only |

## Important behavioral notes
- Changes are BUFFERED — device defers applying until no CID is currently pressed
- Temporary divert takes priority over persistent divert
- remap=0 means "keep previous remap" (not "clear remap"); to clear, remap to own CID
- resetAllCidReportSettings (fn [5]) clears all diversions at once, also buffered
