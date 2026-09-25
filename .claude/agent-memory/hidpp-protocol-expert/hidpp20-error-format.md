---
name: hidpp20-error-format
description: HID++ 2.0 (feature-based) error response byte layout and error code table — applies to every feature, not just one
metadata:
  type: reference
---

## HID++ 2.0 error response — general format (applies to ANY feature call)
Sources (live-fetched 2026-09, no local PDF available this session — see [[doc-sources]]):
- Linux kernel `drivers/hid/hid-logitech-hidpp.c` (`__do_hidpp_send_message_sync`,
  `struct fap { u8 feature_index; u8 funcindex_clientid; u8 params[...]; }`)
- Solaar `lib/logitech_receiver/hidpp20_constants.py` (`ErrorCode` enum)

Raw 20-byte long report, in this codebase's `raw_event[]` indexing:

| raw_event index | field | value on error |
|---|---|---|
| 0 | report ID | 0x11 |
| 1 | device index | echoed |
| 2 | feature_index | **0xFF — fixed marker that this is an error, not a normal reply** |
| 3 | funcindex_clientid | echoes the `(function<<4)\|sw_id` byte from the request that failed |
| 4 (= payload[0]) | params[0] | echoes the **feature index** that was being called (the real one, not 0xFF) |
| 5 (= payload[1]) | params[1] | **error code** |

CleverSwitch's own `parser.py` already implements this exactly: `feature_id == 0xFF` check, then
`error_code = raw_event[5]` → `HidppErrorEvent(slot, pid, sw_id, error_code)` (confirmed by reading
`src/cleverswitch/parser/parser.py` lines ~48 and ~54-57, 2026-09).

## Error code table (`ErrorCode` in Solaar's `hidpp20_constants.py`)
| Value | Name |
|---|---|
| 0x01 | UNKNOWN |
| 0x02 | INVALID_ARGUMENT |
| 0x03 | OUT_OF_RANGE |
| 0x04 | HARDWARE_ERROR |
| 0x05 | LOGITECH_ERROR (internal) |
| 0x06 | INVALID_FEATURE_INDEX |
| 0x07 | INVALID_FUNCTION (i.e. function index doesn't exist on this feature/version) |
| 0x08 | BUSY |
| 0x09 | UNSUPPORTED |

Relevant to feature-availability questions: calling a function index that a given feature *version*
doesn't implement (e.g. a hypothetical older revision missing a function) yields error code
**0x07 INVALID_FUNCTION** in `HidppErrorEvent.error_code`, with `sw_id` echoed from the original
request so the right `InfoTask`/caller can match it. Calling a feature index that doesn't exist at
all is normally prevented earlier by IRoot's `getFeature` returning feature_index=0 (unsupported) —
you wouldn't get this far. 0x06 INVALID_FEATURE_INDEX would only occur if you raced/guessed a stale
feature index (e.g. after a device FW reset re-assigned indices — see [[x0000-iroot]]).
