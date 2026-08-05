---
name: x1814-change-host
description: Feature 0x1814 CHANGE_HOST byte layout, the undocumented notification behavior, and how to discriminate it from setCurrentHost echoes and from 0x1D4B events
metadata:
  type: reference
---

## Feature 0x1814 — CHANGE_HOST
- Source: `x1814_change_host_v0.pdf` — **no events defined in the spec at all**
- The keyboard notification on Easy-Switch press is unsolicited firmware behaviour, not a
  spec-defined event. Corroborated by Solaar (checked 2026-08): `notifications.py` and
  `hidpp20.py` have ZERO code paths mentioning 0x1814 anywhere — Solaar doesn't handle any
  0x1814 notification either.
- Byte 3 fn nibble (upper) = 0x0 always for the notification; sw_id (lower nibble) is
  firmware-dependent — can be 0x00 OR non-zero (e.g. 0x0D observed on a Windows customer device)
- setCurrentHost (fn=[1]) response/echo has fn nibble = 0x1 (byte3 & 0xF0 == 0x10) — this is the
  key discriminator against notifications
- **Correct filter**: `fn=0 (byte3 & 0xF0 == 0x00)` AND `sw_id != SW_ID (byte3 & 0x0F != 0x08)`
- **Wrong filter**: `sw_id == 0` — rejects devices that send sw_id=0x0D notifications
- **Wrong filter (caused loop)**: `sw_id != SW_ID` alone without fn=0 check — matched
  setCurrentHost echoes (fn=1)
- **Notification payload mirrors getHostInfo response layout** (Table 1, v0 spec):
  - byte[4] = nbHost (informational, do not use for host index)
  - byte[5] = target/new host (0-indexed) — this is what to read
  - byte[6] = flags
- getHostInfo response: byte[4]=nbHost, byte[5]=currHost, byte[6]=flags (same layout)
- setCurrentHost request: byte[4]=target host (fn=1, byte[3]&0xF0==0x10)
- 0x1815 HOSTS_INFO also has zero notification code paths in Solaar — apparently also defines
  no events (not spec-verified this pass, PDF unavailable; Solaar-only corroboration)

## Diagnostic heuristic: is a mystery notification really 0x1814, or actually 0x1D4B?
Use when a claimed feature-index resolution (e.g. "0x1814 at index 0x0A") is in doubt:
- If payload byte0 (report byte4) is 0x00 and the notification is claimed to be an 0x1814
  getHostInfo-mirroring notification, byte0 would be `nbHost` — 0x00 is a strong red flag against
  the 0x1814 hypothesis, since an Easy-Switch keyboard always reports nbHost >= 1 (typically 2-3).
  A clean `status=0x00, request=0x01, reason=0x00` triple (see [[x1d4b-wireless-status]]) is a much
  more natural fit for 0x1D4B than for an 0x1814 host-count/target-host pair.
- Plausible real sequence on an Easy-Switch press: physical key press wakes the RF link with the
  CURRENTLY-linked (soon-to-be-departing) host BEFORE the device executes the actual host switch →
  device may emit 0x1D4B (link re-established) and/or the 0x1B04 diverted-CID notification
  (0xD1/D2/D3) to that same still-current host in the brief window before it disconnects and
  re-pairs with the new target. A departing host legitimately receiving a 0x1D4B-shaped event
  around an Easy-Switch press is plausible, not necessarily a bug.
- If feature_index doesn't line up with payload semantics, suspect a stale/incorrect index
  resolution before assuming a new event type. In CleverSwitch specifically, `DeviceCache`
  persists `available_features` (feature code → index) across daemon restarts; indices are
  stable within a firmware version but WILL shift after a firmware update (see
  [[x0000-iroot]] "Feature index stability") — a cached 0x1814 index surviving a firmware update
  that reshuffled the table is a concrete way to get a stale "feature 0x1814 at index N" log line.

## Host Switch Channel CIDs (0xD1/0xD2/0xD3) sometimes present but NOT divertable
- Solaar issue pwr-Solaar/Solaar#1751 (MX Mechanical Mini, WPID B367): device's getCidInfo for the
  three Host Switch Channel CIDs reports them present (FN, FN-sensitive) but WITHOUT the
  divertable flag bit set, unlike other keys on the same device. Attempting to divert them has no
  effect; the ES press is handled natively by the device firmware and never surfaces as an 0x1B04
  notification to the host at all. Confirmed quirk category (device-model-dependent), NOT
  confirmed for MX Keys S specifically — flag as inferred-by-analogy if cited for MX Keys S.
- MX Keys S Solaar device descriptor (per web search, not independently read from source):
  documented as supporting divert-keys but NOT listed for reprogrammable-keys /
  persistent-remappable-keys settings — consistent with ES CIDs being divertable-only rather than
  fully remappable, matches CleverSwitch's KEY_FLAG_DIVERTABLE / KEY_FLAG_PERSISTENTLY_DIVERTABLE.
