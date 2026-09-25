---
name: hidpp10-notifications
description: Authoritative byte layout of HID++1.0 receiver notifications 0x40 (Device Disconnection) and 0x41 (Device Connection), and the full register 0x00 (Enable HID++ Notifications) bit layout — sourced from the real leaked Logitech spec PDF, not a reconstruction
metadata:
  type: reference
---

## Source (2026-09, CleverSwitch issue #113)
`logitech_hidpp10_specification_for_Unifying_Receivers.pdf` ("Logitech hidpp 1.0 excerpt for
public release"), publicly mirrored at
`https://lekensteyn.nl/files/logitech/logitech_hidpp10_specification_for_Unifying_Receivers.pdf`.
19 pages, fetchable directly via WebFetch (binary PDF — WebFetch cannot parse it itself, but
saves it to a local tool-results cache path that the Read tool CAN then parse, since Read
supports PDF). Use this fetch-then-Read two-step whenever the local `hidpp20 public/` dir is
absent (see [[doc-sources]]) and a HID++1.0-specific question comes up — this is a real,
authoritative Logitech document, not a reconstruction. **Scope caveat, stated explicitly in the
doc's own §2.1**: "This document exposes a subset of the hidpp10 specification that targets the
**Logitech Unifying receiver**" (PID 0xC52B) — it does NOT claim to cover Bolt (0xC548). Treat
any Bolt-specific extrapolation from this doc as "structurally very likely, not textually
confirmed for Bolt" unless independently corroborated (see protocol-type byte note below).

## §3.1 — 0x40 Device Disconnection (receiver-generated notification)
Format: `10 ix 40 r0 00 00 00`
- `ix` = device index
- `r0` = **Disconnection type**: `0x00`=Reserved, `0x01`=Reserved, `0x02`=Device disconnected,
  `0x03..0xFF`=Reserved
- Gated by register 0x00 "Wireless notifications" bit (see below) — same gate as 0x41.
- **Decisive fact for CleverSwitch issue #113 Q1**: this notification DOES have a dedicated
  "reason" byte slot (r0), but Logitech's own public excerpt defines only ONE non-reserved value
  (`0x02`, generic "Device disconnected"). There is no `0x02`-vs-`0x03` style split for
  "deliberately switched host" vs "link lost/out of range/battery/sleep" anywhere in this table —
  every value that could carry that distinction is in the Reserved range. The field exists as a
  placeholder Logitech never populated (in this public excerpt), not a confirmed absence of the
  concept, but from the host's perspective it is currently unusable for that purpose.

## §3.2 — 0x41 Device Connection (receiver-generated notification)
Format: `10 ix 41 r0 r1 r2 r3`
- `ix` = device index
- `r0` = bits[0..2] **Protocol type** (`0x04` = Unifying; bits[3..7] Reserved in this doc, i.e.
  the doc only defines a 3-bit field because it only ever needs to say "Unifying")
- `r1` = **Device Info** byte:
  - bits[0..3] = Device Type: `0x00`=Unknown, `0x01`=Keyboard, `0x02`=Mouse, `0x03`=Numpad,
    `0x04`=Presenter, `0x05-07`=Reserved, `0x08`=Trackball, `0x09`=Touchpad, `0x0A-0F`=Reserved
  - bit4 (`0x10`) = Software Present flag — **echoes register 0x00, r1, bit3** (see below)
  - bit5 (`0x20`) = Encryption Status: 0=not encrypted, 1=encrypted
  - bit6 (`0x40`) = **Link Status: 0=Link established (in range), 1=Link not established (out of
    range)** — this is the connect/disconnect discriminator inside 0x41 itself
  - bit7 (`0x80`) = "Connection reason": 0=packet without payload, 1=packet with payload — this is
    NOT a disconnect-cause field; it flags whether this notification packet has an attached HID
    input-report payload riding along (e.g. device just woke the link with a real keypress),
    unrelated to WHY a link came up or went down. Do not conflate with a "reason code".
- `r2` = Wireless PID LSB, `r3` = Wireless PID MSB
- **Decisive fact for Q1**: bit6 (Link Status) is a bare boolean (established/not established).
  There is no reason/cause field anywhere in 0x41 distinguishing "device intentionally switched to
  another host" from "link lost due to range/battery/sleep timeout". Combined with the 0x40 finding
  above: **neither of the two HID++1.0 receiver-level notifications that can signal a departure
  carries a usable intent/reason discriminator in the publicly documented spec.** PR #112's
  input-activity-heuristic approach is not working around a gap that could instead be closed by a
  known undocumented bit — the bit genuinely doesn't exist in what Logitech has published.

## Full decode of the CleverSwitch #113 capture `10 01 41 10 41 78 b3`
- byte0 `0x10`=report id (short), byte1 `0x01`=ix (device index), byte2 `0x41`=sub-id
- byte3 `0x10`=r0 (protocol type byte). `0x10 & 0x07` (the doc's defined 3-bit mask) = `0x00`,
  which does NOT equal the doc's only defined value `0x04`=Unifying — i.e. `0x10` sits entirely
  outside the 3-bit field the Unifying-only doc defines. This is consistent with (not proof of,
  since Bolt isn't in-scope for this doc) Bolt using a wider/different protocol-type encoding than
  Unifying's 3-bit scheme — matches the reporter's own hypothesis that byte3=0x10 is a
  Bolt-specific protocol-type marker, distinct from Unifying's 0x04. No source found that
  tabulates Bolt's protocol-type byte values exhaustively; flag as "structurally confirmed to be
  the protocol-type field, exact Bolt value semantics unconfirmed" rather than a settled fact.
- byte4 `0x41`=r1 (Device Info): bits[0..3]=`0x1`=Keyboard (matches MX Keys S) · bit4=0 (SW
  Present echo off) · bit5=0 (not encrypted / not meaningful here) · **bit6=1 → Link NOT
  established** · bit7=0 (no payload attached)
- byte5-6 `78 b3` = wireless PID LSB/MSB → `0xB378`, exact match for MX Keys S.
- Net: this is a **link-loss report for the keyboard's own connection on the departing host**,
  carried on sub-id 0x41 (not the dedicated 0x40), with zero cause information beyond "not
  established anymore". CleverSwitch's own parser (`src/cleverswitch/parser/parser.py`) decodes
  this identically: `device_type = r1 & 0x0F`, `link_established = (r1 & 0x40) == 0` — confirmed
  byte-exact correct against the real spec table, not just plausible-looking code.

## §4.1 — Register 0x00, "Enable HID++ Notifications" (receiver register, NOT feature notification gating)
Read: `10 ix 81 00 00 00 00` → response `10 ix 81 00 r0 r1 r2`
Write: `10 ix 80 00 p0 p1 p2` (p0/p1/p2 same bit layout as r0/r1/r2)
All bits: `0`=disabled (power-up default), `1`=enabled.

| Field | Bit | Name | Effect when enabled |
|---|---|---|---|
| r0 (Devices) | 4 | **Battery Status** | device battery-status notifications reported |
| r0 | 0-3,5-7 | Reserved | — |
| r1 (Receiver) | 0 | **Wireless notifications** | "Device arrival, removal, are reported by HID++ notif. 0x40, 0x41" (verbatim table text) |
| r1 | 3 | **Software Present** | echoed back in every 0x41's Device Info byte4 |
| r1 | 1,2,4-7 | Reserved | — |
| r2 (Devices, cont'd) | all | Reserved | — |

CleverSwitch's `ENABLE_HIDPP_NOTIFICATIONS_MESSAGE` (`receiver_trigger.py`) writes p0=0x00,
p1=0x09 (bit0+bit3 = wireless notifications + software present), p2=0x00 — exactly matches the
documented "arm before enumerating" pattern, confirmed correct.

## Decisive fact for Q3 — register 0x00 does NOT gate device-originated HID++2.0 feature notifications
Per this table, register 0x00's ONLY documented effects are: (a) receiver battery-status pushes,
(b) the 0x40/0x41 receiver-generated connect/disconnect pair, (c) the software-present echo bit.
**There is no bit anywhere in register 0x00 controlling whether HID++2.0 long-report feature
notifications from an already-connected device (e.g. 0x1814 fn0, 0x1B04 analyticsKeyEvt, 0x1D4B)
get forwarded.** Per §2.5.1 "Spontaneous Information Delivery" (p.3 of the same doc): once a
device is connected, "HID reports... Battery status, F-Lock status, etc... Receiver messages
(device arrival, departure, etc.)" are simply forwarded — device-originated HID++ reports are
described as generic interrupt-channel passthrough, not something register 0x00 selectively
filters per-feature. **This means a receiver silently swallowing 0x1814 while still forwarding
0x41, purely due to a register-0x00 flag-state difference, has no support in the documented
architecture** — the two notification classes (receiver-generated 0x40/0x41 vs device-originated
HID++2.0 feature notifications) are architecturally separate paths, only the former is gated by
this register. Caveat: this doc is Unifying-scoped (§2.1); Bolt could theoretically have an
undocumented additional register-0x00 bit not covered here, but there's no evidence for one, and
CleverSwitch's r1=0x09 write already sets every bit this doc says is relevant.

## Much stronger, protocol-external candidate for "0x1814 silently missing on one Linux Bolt unit but not another": Linux kernel hid-logitech-dj interface-routing bug (2026-09, active LKML thread, NOT yet confirmed merged)
Found via a September 2026 kernel.org mailing-list patch thread (`ratatoskr.run/linux-input`
archive mirror), originally for an MX Master 4 hi-res-scroll bug, but with a root cause that is
directly relevant here:
- Bolt receiver support was added by commit `022eb347ff3a` ("HID: logitech: add Bolt receiver
  support"). That commit only claimed the DJ/receiver-control USB interface (interface 2) as a
  proper "dj" HID++ interface; **interfaces 0 and 1 (boot keyboard / boot mouse) registered as
  plain generic-HID input devices instead of being claimed by the dj driver.**
- Quoted root-cause description from the fix thread: *"Interface 1 therefore registers an input
  device of its own, and the paired device's reports are never forwarded to the dj child device,
  which ends up receiving nothing at all"* — and for interface 0 specifically: *"interface 0
  returned early as a generic-hid device"*, dropping forwarding of unnumbered (keyboard) reports.
- The fix sets `no_dj_interfaces = 3` so all three Bolt interfaces get claimed as DJ/HID++
  interfaces and their traffic is properly demultiplexed to the per-paired-device hidraw/input
  node that userspace (CleverSwitch, Solaar, etc.) actually reads.
- **Why this is a strong candidate for #113's discrepancy specifically**: 0x40/0x41 receiver
  notifications originate on interface 2 (receiver control), which was *always* correctly claimed
  — consistent with the reporter seeing 0x41 fine. A device-originated HID++2.0 feature
  notification (0x1814 fn0) for a KEYBOARD would traverse interface 0 in the affected kernel
  versions — exactly the interface this bug describes as silently discarding reports pre-patch.
  This produces precisely the observed asymmetry (0x41 present, 0x1814 absent) via a kernel
  routing defect, with zero need to invoke firmware differences or EES coupling state at all.
- **Confidence and caveats**: this is a real, dated (2026-09-01) upstream discussion with a named
  root-cause commit, high relevance — but (a) not confirmed merged/released into a shipping
  kernel as of this writing, (b) only explains a Linux-side null result, not a macOS one — if
  reporter #113's negative capture was on macOS, this explanation doesn't apply, (c) the thread's
  own primary complaint is about a mouse (interface 1 / scroll wheel), and MX Keys S is a
  keyboard on interface 0 — a second thread snippet confirms interface 0 has the same "returned
  early as generic-hid" defect for unnumbered reports, but exact behavior for HID++2.0 long
  reports (0x11) specifically on interface 0, as opposed to the unnumbered boot-keyboard report,
  was not directly quoted from source and should be treated as an inference, not a verified line
  of code read. Sources: `https://ratatoskr.run/linux-input/2026/09/17492849/t`,
  `https://ratatoskr.run/linux-input/2026/07/17247095/t`,
  `https://ratatoskr.run/sashiko-reviews/2026/09/17493541`.
- **Actionable diagnostic** (fact, not a fix design): if reporter #113 is on Linux, checking
  `uname -r` for whether their kernel predates this fix, and counting hidraw nodes exposed for
  the Bolt receiver's USB device (`ls /sys/class/hidraw` cross-referenced against
  `lsusb -t`/`udevadm info`) — a receiver exposing fewer hidraw children than expected (interfaces
  not separately enumerated as dj children) would be the fingerprint of this bug. This is a
  protocol/diagnostic fact for whoever designs the fix, not a design decision itself.
