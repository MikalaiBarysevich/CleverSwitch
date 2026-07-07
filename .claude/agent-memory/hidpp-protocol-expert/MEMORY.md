# HID++ Protocol Expert Memory

## Key doc files
- `logitech_hidpp_hid_vendor_collection_usages.pdf` — legacy (0xFF00) vs modern (0xFF43) collection schemes, report sizes
- `logitech_hidpp_2.0_specification_draft_2012-06-04.pdf` — HID++ 2.0 full spec including transaction log example
- `Logitech_hidpp10_specification_draft_for_unifying_receivers.docx` — HID++ 1.0 spec (BINARY, cannot be read with Read tool)
- `Unifying_receiver_DJ_collection_specification_draft.docx` — DJ spec (BINARY, cannot be read with Read tool)

## Critical: HID++ 2.0 response format
**ALL HID++ 2.0 responses are LONG (report 0x11, 20 bytes), even when the request was SHORT (0x10).**
Confirmed by the transaction log in the spec (C52B Unifying receiver):
- `X 10 ... GetFeature(0x0003)` → `R 11 ...` (always long)
- `X 10 ... GetFwInfo` → `R 11 ...` (always long)

## Windows collection routing (legacy scheme, usage_page 0xFF00)
- Unifying (0xC52B) and Bolt (0xC548) use legacy scheme
- Three separate logical HID devices on Windows:
  - `usage=0x0001`: short collection — report 0x10, 7 bytes, Input+Output
  - `usage=0x0002`: long collection — report 0x11, 20 bytes, Input+Output
  - `usage=0x0004`: DJ collection — report 0x20
- Windows routes input reports by report ID to the collection that owns that report ID
- **Must open long collection to receive HID++ 2.0 responses** (always 0x11)
- Cleanest strategy: send all HID++ 2.0 requests as long 0x11 (zero-pad), open only long collection for r/w; open DJ collection separately for device-arrival events

## HID++ 1.0 register sub_ids
- 0x81: GET_SHORT_REGISTER request; 0x81 response on short 0x10 report
- 0x82: SET_LONG_REGISTER (write)
- 0x83: GET_LONG_REGISTER request; 0x83 response on LONG 0x11 report
- 0x8F: ERR_MESSAGE (short 0x10 report)

## Feature 0x1D4B — Wireless Device Status (v0)
- Source: `x1d4b_wireless_device_status_v0.pdf`
- Single event only: `WirelessDeviceStatusBroadcastEvent` (event0, byte3=0x00)
- **Always enabled** — no subscription needed; device sends unconditionally on power-on reset
- Payload (bytes 4–6 of the long report):
  - byte4 status: 0x00=unknown, 0x01=reconnection
  - byte5 request: 0x00=no request, 0x01=software reconfiguration needed
  - byte6 reason: 0x00=unknown, 0x01=power-switch activated
- `request=0x01` means volatile config (diverted keys, etc.) was lost — re-apply settings now
- Arrives AFTER DJ connect event; wait for 0x1D4B before sending feature commands on reconnect
- Arrives on long collection (report 0x11), NOT on DJ collection (report 0x20)

## Feature 0x1B04 — REPROG_CONTROLS_V4 (v6)
- Source: `x1b04_specialkeysmsebuttons_v6.pdf` (15 pages, use pages:"1-15")
- Also `x1b04_specialkeysmsebuttons_v4.pdf` — older version
- setCidReporting = function [3], byte3 = 0x3N (fn=3, sw_id in low nibble)
- Response **echoes the request exactly** (including byte3 fn|sw_id) — not a new event format
- See `x1b04-setCidReporting.md` for full byte layout and bfield decode table

## Divert persistence and reset semantics (x1b04 v6, p7-9)
- **Temporary divert** (`divert=1, dvalid=1`, bfield=0x03): RAM-only; cleared on every HID++ configuration reset
- **Persistent divert** (`persist=1, pvalid=1`, bfield=0x0C): survives resets; stored in NV memory
- **Both** (`bfield=0x0F`): active immediately AND survives resets — recommended for CleverSwitch
- A "HID++ configuration reset" is defined by feature 0x0020 (doc not in repo). Known triggers:
  - Device power-on / battery insert
  - Host switch: 0x1814 setCurrentHost says "device will most probably reset"
  - RF reconnection (deep sleep wake, link loss recovery)
- 0x1D4B `request=0x01` is the authoritative signal that volatile HID++ config was lost → re-apply

## setCidReporting is BUFFERED (x1b04 v6, Table 6 NOTE)
- The divert flag is NOT applied immediately; device queues it until no CID is currently pressed
- Same applies to resetAllCidReportSettings (fn [5])
- Creates a timing window: ack received but divert not yet active; press in this window goes native

## resetAllCidReportSettings (fn [5] of 0x1B04)
- Clears ALL diversions at once; response has NO per-CID payload
- NOT detected by ExternalUndivertEvent logic in parse_message — this is a known gap

## 0x1D4B feature index NOT guaranteed to be 0x04
- parse_message hard-codes `feature_id == 0x04` for 0x1D4B detection — this is a latent bug
- The actual index is firmware-assigned; must be resolved via getFeature(0x1D4B) and stored in LogiProduct
- If wrong, all reconnect events are silently missed and ES keys are never re-diverted

## Feature index stability
- Feature indices are stable within a firmware version (ROM-based feature table)
- They only change after a firmware update, not on reconnect or host switch
- Safe to cache for lifetime of PathListener/LogiProduct

## x0000 IRoot (v2)
- Source: `x0000_root_v2.pdf`
- getFeature(featId) → featureIndex (0=not found, 1-N=index), featureType, featureVersion
- featureType bits: bit7=obsolete, bit6=hidden, bit5=engineering, bit4=manuf_deact, bit3=compl_deact
- Feature indices are one-based; 0 means not found

## Feature 0x1814 — CHANGE_HOST notification (non-divertable keyboards)
- Source: `x1814_change_host_v0.pdf` — **no events defined in the spec at all**
- The keyboard notification on Easy-Switch press is unsolicited firmware behaviour, not a spec-defined event
- Byte 3 fn nibble (upper) = 0x0 always (notification); sw_id (lower nibble) is firmware-dependent — can be 0x00 OR non-zero (e.g. 0x0D observed on Windows customer device)
- setCurrentHost (fn=[1]) response/echo has fn nibble = 0x1 (byte3 & 0xF0 == 0x10) — this is the key discriminator against notifications
- **Correct filter**: `fn=0 (byte3 & 0xF0 == 0x00)` AND `sw_id != SW_ID (byte3 & 0x0F != 0x08)`
- **Wrong filter**: `sw_id == 0` — rejects devices that send sw_id=0x0D notifications
- **Wrong filter (caused loop)**: `sw_id != SW_ID` alone without fn=0 check — matched setCurrentHost echoes (fn=1)
- **Notification payload mirrors getHostInfo response layout** (Table 1, v0 spec):
  - byte[4] = nbHost (informational, do not use for host index)
  - byte[5] = target/new host (0-indexed) — this is what to read
  - byte[6] = flags
- getHostInfo response: byte[4]=nbHost, byte[5]=currHost, byte[6]=flags (same layout)
- setCurrentHost request: byte[4]=target host (fn=1, byte[3]&0xF0==0x10)

## `hidpp20 public/` doc dir is gitignored — may be ABSENT in a given sandbox
- Confirmed via `.gitignore:165` (`hidpp20 public/`). It's a local-only doc cache, not committed.
- When it's missing (check with Glob before assuming), fall back to Solaar's reference
  implementation (`raw.githubusercontent.com/pwr-Solaar/Solaar/master/lib/logitech_receiver/hidpp20.py`)
  — this project's own `hidpp/constants.py` header cites Solaar as a co-source alongside the spec PDFs.
- `github.com/Logitech/cpg-docs/hidpp20` is Logitech's *official* public mirror but only ships
  `features/0x0000-IRoot.rst` as a worked example — not a full feature-by-feature doc set. Not useful
  for looking up individual feature byte layouts beyond IRoot.

## Features 0x0005 (DEVICE_TYPE_AND_NAME) / 0x0007 (DEVICE_FRIENDLY_NAME) string quirk
- Verified against Solaar's current `hidpp20.py` (master, checked 2026-07): its `get_name()` and
  `get_friendly_name()` trust the fn[0] count/length byte exactly and do NOT strip/truncate at NUL —
  same behavior as this project's `get_device_name_task.py` / `get_device_friendly_name_task.py`.
  This is a **shared latent gap with upstream**, not a divergence — no upstream fix to crib from.
- Byte layout confirmed consistent both projects: 0x0005 getDeviceName response has raw name bytes
  starting at payload byte 0 (no echo byte); 0x0007 getFriendlyName response has byte0 = echoed
  byteIndex, name bytes start at payload byte 1 (up to 15 bytes/call vs 16 for 0x0005).
- Could NOT verify the literal spec wording on NUL-termination/padding semantics for fn[0]'s count
  (local `hidpp20 public/` PDFs absent this session, and Logitech's cpg-docs mirror doesn't cover
  these features). Recommendation given was reasoned from protocol convention + real-world firmware
  failure modes, not a direct doc quote — flag this distinction if asked again with docs available.
- Recommended sanitization: truncate-at-first-NUL on the raw byte buffer before UTF-8 decode, not
  `rstrip(b'\x00')` — a partial-overwrite-of-flash-buffer firmware bug (shorter name written into a
  buffer previously holding a longer one, without zeroing the tail) can leave stale non-zero garbage
  *after* the first NUL, which rstrip would not remove but truncate-at-first-NUL does. Embedded NULs
  are never legitimate in a Logitech device/friendly name (always short printable marketing strings).

## See also
- `windows-collections.md` — detailed table of which collection to open for each operation
- `x1b04-setCidReporting.md` — setCidReporting byte layout and bfield decode
