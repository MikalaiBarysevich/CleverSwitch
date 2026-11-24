# HID++ documentation sources

The official Logitech HID++ documents are **not** committed to this repository, and `hidpp20 public/` is listed in `.gitignore`. Keep a local copy outside version control and pass its path to the agent when asking protocol questions.

## What to keep locally

A directory of the published HID++ 2.0 feature documents, one per feature code, plus the HID++ 1.0 register notes. They are named after the feature they describe, so a feature code maps to a filename prefix (`0x1814` → `x1814…`). When you add or move the collection, record the path here.

## Lookup procedure

1. Find the local collection:
   ```bash
   find ~ -maxdepth 4 -type d -name 'hidpp20 public' 2>/dev/null
   ```
2. Match the feature code to a document by its filename prefix.
3. Read the section for the function you need — the documents carry the request and response byte layouts, error codes and per-version differences.
4. Cross-check against `src/cleverswitch/hidpp/` for how this project encodes it.

## Fallbacks when the documents are unavailable

- `src/cleverswitch/hidpp/constants.py` — feature codes, bit masks, PIDs and SW IDs already in use.
- `src/cleverswitch/parser/parser.py` — the report formats the daemon actually receives.
- `tests/cleverswitch/hidpp/` — worked examples of message construction.
- `.agents/memory/hidpp-protocol/` — local, uncommitted notes. Useful for orientation, not authoritative.

If none of these answer the question, say so rather than guessing.
