---
name: hidpp-protocol
description: Authoritative reference for Logitech HID++ 1.0/2.0 protocol details — feature codes, message and report layouts, register access, error codes, device pairing, Bolt/Unifying receiver behaviour, Bluetooth HID++ and host switching. Use for any question about how a HID++ message is built, parsed or addressed, before writing protocol code.
---

# HID++ Protocol Reference

You are working with the Logitech HID++ protocol. Answer at the byte level and never guess a field, opcode or offset.

## Sources, in order

1. **Official Logitech HID++ documentation.** It is not committed to this repository (the `hidpp20 public/` directory is gitignored). Locate the local copy with `find ~ -maxdepth 4 -type d -name 'hidpp20 public' 2>/dev/null`, or ask the user where it lives. `references/doc-sources.md` records what to look for.
2. **Local notes.** If `.agents/memory/hidpp-protocol/` exists in this checkout, read `MEMORY.md` first and then the topic file for the feature (for example `x1814-change-host.md`, `x1b04-setCidReporting.md`). These notes are uncommitted working memory: consult them, do not treat them as authoritative when a PDF disagrees.
3. **Existing code.** `src/cleverswitch/hidpp/` (`constants.py`, `protocol.py`, `transport.py`) and the parser show how this project already encodes the messages.

Read the relevant file before answering. If the documentation cannot be found, say so explicitly instead of reconstructing the format from memory.

## Response guidelines

- Be precise: exact byte positions, bit masks, report IDs, feature indices, function indices, parameter layouts.
- Use hex for every protocol value (`0x1814`, `0x00`, `0xFF`).
- Show byte layouts when relevant:

  ```
  Byte 0: Report ID (0x11 long, 0x10 short, 0x20 DJ)
  Byte 1: Device index
  Byte 2: Feature index
  Byte 3: Function ID << 4 | SW ID
  Bytes 4-6 / 4-19: parameters
  ```

- Cite the file or section the answer comes from.
- Distinguish short (7 byte), long (20 byte) and very long (64 byte) reports.
- Note HID++ 1.0 register access vs HID++ 2.0 feature access when it changes the answer.
- Say whether a message is addressed to the receiver itself or forwarded to a device index.

## Orientation

- Logitech vendor id `0x046D`; Bolt receiver pid `0xC548`.
- Device index `0xFF` is the receiver itself, and also the slot used for Bluetooth direct connections.
- HID++ 2.0 is feature-indexed: resolve a feature code through IRoot (`0x0000`) before calling its functions.
- `0x1B04` `setCidReporting` responses are a verbatim echo of the request; a cleared field in the echo is a rejection signal.
- The SW ID nibble has bit 3 set, so 8–15 is the whole space, and this project has already allocated all of it (see `hidpp/constants.py` and `subscriber/task/constants.py`).

## Features this project depends on

- `0x0000` IRoot — feature index resolution
- `0x0003` Device FW Version
- `0x1814` CHANGE_HOST — host switching
- `0x1815` HOSTS_INFO — host information
- `0x1B04` REPROG_CONTROLS_V4 — CID remapping, diversion, Easy-Switch reporting
- `0x1D4B` Wireless Status — connection and battery reporting

## Never

- Fabricate protocol details. Say the answer is unknown when the sources do not cover it.
- Confuse HID++ 1.0 register access with HID++ 2.0 feature access.
- Produce a code implementation unless asked — answer at the protocol level.
- Edit `.agents/memory/` from a shared or CI context; it is local-only and untracked.
