# HID++ Protocol Expert Memory

## Index
- [Doc sources](doc-sources.md) — where to find HID++ docs (local PDFs vs Solaar vs cpg-docs), gaps found
- [Windows collections](windows-collections.md) — which HID collection (0x10/0x11/0x20) to open for each op
- [x0000 IRoot](x0000-iroot.md) — getFeature() lookup semantics, feature-index stability
- [x1814 CHANGE_HOST](x1814-change-host.md) — undocumented notification behavior, filter logic, 1814-vs-1D4B diagnostic heuristic
- [x1B04 setCidReporting](x1b04-setCidReporting.md) — byte layout, bfield decode, divert persistence/buffering
- [x1D4B WIRELESS_DEVICE_STATUS](x1d4b-wireless-status.md) — event payload layout, reset-trigger semantics

## Critical: HID++ 2.0 response format
**ALL HID++ 2.0 responses are LONG (report 0x11, 20 bytes), even when the request was SHORT (0x10).**
Confirmed by the transaction log in `logitech_hidpp_2.0_specification_draft_2012-06-04.pdf`
(C52B Unifying receiver): `X 10 ... GetFeature(0x0003)` → `R 11 ...`; `X 10 ... GetFwInfo` → `R 11 ...`.

## Software ID (sw_id) convention — applies to EVERY HID++ 2.0 feature, not just one
Byte 3 lower nibble = sw_id. Per the actual spec text (Software ID field,
`logitech_hidpp_2.0_specification_draft_2012-06-04.pdf`): *"0 Do not use (allows to distinguish a
notification from a response)."* Compliant software must use non-zero sw_id (1-15); firmware
echoes that sw_id back in responses. Consequence: **sw_id==0 is a universal, spec-guaranteed
marker for "unsolicited device notification"** — never a reply to anyone's request. A packet with
fn matching some function-index but sw_id!=0 is always a response/reply (to whichever software
owns that sw_id), never a notification — regardless of feature. CleverSwitch's own
`hidpp/constants.py` codifies this exact rule in a comment (line ~41: "Notifications from device
have sw_id=0, so bit 3 distinguishes our responses"). Filtering "genuine notification" must check
sw_id==0 specifically, not merely "!= my own sw_id" (see [[x1814-change-host]] for a concrete loop
bug caused by the weaker check).

## HID++ 1.0 register sub_ids
- 0x81: GET_SHORT_REGISTER request; 0x81 response on short 0x10 report
- 0x82: SET_LONG_REGISTER (write)
- 0x83: GET_LONG_REGISTER request; 0x83 response on LONG 0x11 report
- 0x8F: ERR_MESSAGE (short 0x10 report)

## Key doc files (in `hidpp20 public/`, when present — see [doc-sources.md](doc-sources.md))
- `logitech_hidpp_hid_vendor_collection_usages.pdf` — legacy (0xFF00) vs modern (0xFF43) schemes
- `logitech_hidpp_2.0_specification_draft_2012-06-04.pdf` — HID++ 2.0 full spec + transaction log
- `x0000_root_v2.pdf`, `x1814_change_host_v0.pdf`, `x1b04_specialkeysmsebuttons_v6.pdf`,
  `x1d4b_wireless_device_status_v0.pdf`
- `Logitech_hidpp10_specification_draft_for_unifying_receivers.docx`,
  `Unifying_receiver_DJ_collection_specification_draft.docx` — BOTH BINARY, cannot use Read tool
