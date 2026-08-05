---
name: doc-sources
description: Where to find HID++ documentation (local PDFs vs Solaar vs Logitech cpg-docs), and known gaps between them
metadata:
  type: reference
---

## `hidpp20 public/` doc dir is gitignored — may be ABSENT in a given sandbox
- Confirmed via `.gitignore:165` (`hidpp20 public/`). It's a local-only doc cache, not committed.
- When missing (check with Glob before assuming), fall back to Solaar's reference implementation
  (`raw.githubusercontent.com/pwr-Solaar/Solaar/master/lib/logitech_receiver/hidpp20.py` and
  `.../notifications.py`) — this project's own `hidpp/constants.py` header cites Solaar as a
  co-source alongside the spec PDFs.
- `github.com/Logitech/cpg-docs/hidpp20` is Logitech's *official* public mirror but only ships
  `features/0x0000-IRoot.rst` as a worked example — not a full feature-by-feature doc set. Not
  useful for looking up individual feature byte layouts beyond IRoot.

## Known doc/behavior gaps confirmed against Solaar (checked 2026-08)
- 0x1814 (CHANGE_HOST): zero notification handling in Solaar — see [[x1814-change-host]]
- 0x1815 (HOSTS_INFO): zero notification handling in Solaar either (not spec-verified this pass)
- 0x1D4B (WIRELESS_DEVICE_STATUS): Solaar's byte semantics match this project's — see
  [[x1d4b-wireless-status]]

## Features 0x0005 (DEVICE_TYPE_AND_NAME) / 0x0007 (DEVICE_FRIENDLY_NAME) string quirk
- Verified against Solaar's current `hidpp20.py` (master, checked 2026-07): its `get_name()` and
  `get_friendly_name()` trust the fn[0] count/length byte exactly and do NOT strip/truncate at
  NUL — same behavior as this project's `get_device_name_task.py` / `get_device_friendly_name_task.py`.
  Shared latent gap with upstream, not a divergence — no upstream fix to crib from.
- Byte layout confirmed consistent both projects: 0x0005 getDeviceName response has raw name
  bytes starting at payload byte 0 (no echo byte); 0x0007 getFriendlyName response has byte0 =
  echoed byteIndex, name bytes start at payload byte 1 (up to 15 bytes/call vs 16 for 0x0005).
- Could NOT verify the literal spec wording on NUL-termination/padding semantics for fn[0]'s
  count (local PDFs absent, and Logitech's cpg-docs mirror doesn't cover these features).
  Recommendation given was reasoned from protocol convention + real-world firmware failure modes,
  not a direct doc quote — flag this distinction if asked again with docs available.
- Recommended sanitization: truncate-at-first-NUL on the raw byte buffer before UTF-8 decode, not
  `rstrip(b'\x00')` — a partial-overwrite-of-flash-buffer firmware bug (shorter name written into
  a buffer previously holding a longer one, without zeroing the tail) can leave stale non-zero
  garbage *after* the first NUL, which rstrip would not remove but truncate-at-first-NUL does.
  Embedded NULs are never legitimate in a Logitech device/friendly name.
