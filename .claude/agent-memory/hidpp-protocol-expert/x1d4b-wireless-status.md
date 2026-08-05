---
name: x1d4b-wireless-status
description: Feature 0x1D4B WIRELESS_DEVICE_STATUS event payload layout, reset-trigger semantics, and Solaar's matching byte handling
metadata:
  type: reference
---

## Feature 0x1D4B — Wireless Device Status (v0)
- Source: `x1d4b_wireless_device_status_v0.pdf`
- Single event only: `WirelessDeviceStatusBroadcastEvent` (event0, byte3=0x00)
- **Always enabled** — no subscription needed; device sends unconditionally on power-on reset
- Payload (bytes 4-6 of the long report):
  - byte4 status: 0x00=unknown, 0x01=reconnection
  - byte5 request: 0x00=no request, 0x01=software reconfiguration needed
  - byte6 reason: 0x00=unknown, 0x01=power-switch activated
- `request=0x01` means volatile config (diverted keys, etc.) was lost — re-apply settings now
- Arrives AFTER DJ connect event; wait for 0x1D4B before sending feature commands on reconnect
- Arrives on long collection (report 0x11), NOT on DJ collection (report 0x20)
- 0x1D4B `request=0x01` is the authoritative signal that volatile HID++ config was lost →
  re-apply (ties into divert reset semantics, see [[x1b04-setCidReporting]])

## Solaar corroboration (checked 2026-08, notifications.py)
- Solaar's `notifications.py` handler: `notification.data[0]`=status, `data[1]==1`→
  reconfiguration request (triggers `device.changed()` + `apply_settings_if_needed()`),
  `data[2]==1`→reason "powered on". `notification.data` == raw report bytes[4:], i.e.
  data[0]=byte4, data[1]=byte5, data[2]=byte6. Matches the byte4/5/6 status/request/reason
  mapping above exactly — independent confirmation of the layout.

## Feature index NOT guaranteed to be any fixed value (was 0x04 in an older codebase revision)
- An older revision of the parser hard-coded `feature_id == 0x04` for 0x1D4B detection — this was
  a latent bug. The actual index is firmware-assigned per device; must be resolved via
  getFeature(0x1D4B) and cached per-device (see [[x0000-iroot]] for IRoot lookup, and
  CleverSwitch's `WirelessStatusSubscriber` which uses payload-signature + elimination against
  `device.available_features.values()` instead of a hardcoded index — see repo
  `src/cleverswitch/subscriber/wireless_status_subscriber.py`).
- If the index used is wrong, all reconnect events are silently missed and ES keys are never
  re-diverted.
