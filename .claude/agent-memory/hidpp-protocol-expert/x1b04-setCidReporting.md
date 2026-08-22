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

## Divert persistence and reset semantics (x1b04 v6, p7-9)
- **Temporary divert** (`divert=1, dvalid=1`, bfield=0x03): RAM-only; cleared on every HID++
  configuration reset
- **Persistent divert** (`persist=1, pvalid=1`, bfield=0x0C): survives resets; stored in NV memory
- **Both** (`bfield=0x0F`): active immediately AND survives resets — recommended for CleverSwitch
- A "HID++ configuration reset" is defined by feature 0x0020 (doc not in repo). Known triggers:
  - Device power-on / battery insert
  - Host switch: 0x1814 setCurrentHost says "device will most probably reset"
  - RF reconnection (deep sleep wake, link loss recovery)
- 0x1D4B `request=0x01` is the authoritative signal that volatile HID++ config was lost →
  re-apply (see [[x1d4b-wireless-status]])

## setCidReporting is BUFFERED (x1b04 v6, Table 6 NOTE)
- The divert flag is NOT applied immediately; device queues it until no CID is currently pressed
- Same applies to resetAllCidReportSettings (fn [5])
- Creates a timing window: ack received but divert not yet active; press in this window goes native

## resetAllCidReportSettings (fn [5] of 0x1B04)
- Clears ALL diversions at once; response has NO per-CID payload
- An older codebase revision's ExternalUndivertEvent logic did not detect this case — known gap
  at that time; re-verify current `parser.py` if relevant.

## analyticsKeyEvt vs divert: does analytics suppress the native action? (2026-08 investigation)
No local PDF and no web mirror (lekensteyn's x1b04 HTML, PixlOne/logiops wiki) documents the
analyticsKeyEvt flag's semantics in prose — it's simply absent from the older mirrors (v6-era
addition). Best evidence is **architectural, not a direct spec quote**:
- Solaar issue #1512 (MX Keys Mini): Host Switch Channel CIDs (0xD1-D3) report flags "FN, FN
  sensitive, analytics key events" — **no divertable, no persistently divertable flag at all**.
  Since there is no divert capability on this device's ES CIDs, analytics key events *cannot* be
  implemented as "divert-then-notify" — it must be a parallel/observational notification that
  coexists with the native (undivertable) action. This is strong indirect proof that
  analyticsKeyEvt is architecturally independent of divert and does NOT suppress the native
  action — Logitech added it specifically so hosts can observe events on controls whose native
  behavior can't be (or isn't meant to be) suppressed.
- Corroborates CleverSwitch's own design choice in `set_report_flag_subscriber.py`: analytics
  mode is preferred unconditionally over divert whenever advertised, precisely because
  CleverSwitch wants the keyboard to keep performing its OWN native Easy-Switch host change
  (so it doesn't have to reimplement that logic) and just wants a heads-up notification to
  mirror to the mouse — the opposite of what divert-mode would give (native switch suppressed).
- By contrast divert (bit0/1 of byte 6) is spec-documented (Table 6/7, this file above) as
  literally replacing the native HID report with an HID++ notification — that suppression
  behavior IS explicit in the v6 spec text, unlike analytics.
- Conclusion given to user: treat as high-confidence *inference*, not a verified spec sentence,
  since the authoritative x1b04 v6 PDF (which does mention analyticsKeyEvt, see byte 9 table
  above) was not locally available this session to check its prose around Table 6 for an
  explicit statement — flag this gap if asked again with local PDFs present.

## Device generation comparison: divertable flag presence on ES CIDs (0xD1/D2/D3)
Confirmed via Solaar GitHub issues (2026-08 web search, not local docs):
- **MX Keys (original, full-size, wpid 4082/408A-ish era)**: ES CIDs report
  "nonstandard, divertable, persistently divertable, analytics key events" — ALL flags present.
  (Solaar wiki "Example: Diverted Host Switch Channel keys", issue #1070.)
- **MX Keys Mini**: ES CIDs report "FN, FN sensitive, analytics key events" only — divertable and
  persistently divertable flags ABSENT. (Solaar issue #1512.)
- **MX Mechanical Mini**: ES CIDs present + FN-sensitive but NOT divertable either (issue #1751,
  already in [[x1814-change-host]]) — same pattern as MX Keys Mini.
- **MX Keys S (wpid 0xB378)**: NOT independently confirmed this session — no raw getCidInfo dump
  or solaar-show output found via web search. By analogy to the Mini/Mechanical-Mini generation
  (newer, smaller-form-factor keyboards), it likely follows the "analytics-only, no divert" flag
  pattern, but this is inference-by-generation, not verified data. Recommend CleverSwitch trust
  its own runtime getCidInfo read over any hardcoded assumption — the code already does this
  (`device.supported_flags` populated by `FindESCidsFlagsTask`), which is the right approach.
- Pattern suggests Logitech's newer firmware increasingly ships ES CIDs as analytics-only
  (non-divertable) — makes sense given the analyticsKeyEvt-does-not-suppress-native conclusion
  above: Logitech doesn't want third-party divert to break Easy-Switch's own host-switch UX, but
  still wants to expose an observation channel to software.
