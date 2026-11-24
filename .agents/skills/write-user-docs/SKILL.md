---
name: write-user-docs
description: Maintain CleverSwitch's user-facing documentation: the root README (feature overview only) and docs/ (installation, configuration, feature guides, troubleshooting). Use when adding or changing a user-visible feature, config key, CLI flag, supported platform, install step or log path; when moving detail out of the README; or when asked to update the README or write docs.
---

# Write user docs

`README.md` sells the product; `docs/` explains it. Keep one source of truth: the README carries a short summary and a link, never a full procedure.

## Where content belongs

| Content | File |
|---|---|
| What it is, headline features, support matrix, quick start, limitations | `README.md` — **repo root, never move it into `docs/`** |
| Install, update, autostart, uninstall | `docs/installation.md` |
| Config file, every key, CLI flags, device cache | `docs/configuration.md` |
| One feature in full (hooks, edge switch, logging) | `docs/features/<feature>.md` |
| "It doesn't work" checks | `docs/troubleshooting.md` |
| Index of all docs | `docs/README.md` |
| Internals: event flow, threading, retries, gotchas | `docs/architecture/<subsystem>.md` |

If a README bullet needs a third sentence, a table or a platform caveat, it belongs in `docs/`. New files are lowercase kebab-case; user docs never go under `docs/architecture/`.

## README rules

- Stays in the repository root, feature-first, target ~100 lines.
- Fixed section order: intro, badges, Features, Quick start, How it works, Supported setups, Good to know, Documentation, Support the project, License.
- Each feature bullet: bold name, 1–2 sentences, relative link to its detail doc.
- Adding a feature updates three places: a Features bullet, a Documentation table row, and a `docs/README.md` index row.
- Keep claims true: tested hardware, transports, supported platforms, known limitations.
- No fake demos or screenshots — only real captures, and only if the user asks for one.
- Relative links in bundled pages must point at files that are also bundled. The archives contain `README.md`, `LICENSE.txt`, `config.example.yaml`, `docs/*.md` and `docs/features/*.md`; everything else — notably `docs/architecture/` and `rules.d/` — needs an absolute GitHub URL.

## Adding a new doc

1. Pick the location from the table above and follow the existing file naming.
2. **Move, don't duplicate.** Remove the detail from the README (or the old doc) in the same change.
3. Keep heading text when other docs link to its anchor; GitHub anchors strip punctuation and backticks, so ``### `/dev/input` access`` is `#devinput-access`.
4. Update every inbound link: `README.md`, `docs/README.md`, `docs/installation.md`, the feature docs, `.agents/skills/release-notes/SKILL.md`, and installer messages that name a doc.
5. If the new file is in a new subdirectory, add it to the release staging step in `scripts/linux/build.sh`, `scripts/mac/build.sh` and `scripts/windows/build.bat`, or its links break in the archive. Current staging copies `docs/*.md` and `docs/features/*.md`. Relative links from bundled pages to files that are not in the archive (notably `docs/architecture/` and `rules.d/`) must be absolute GitHub URLs.
6. Cross-link related pages ("Hooks" ↔ "Edge switch" for `CLEVERSWITCH_SWITCH_SOURCE`).

## Updating the README after a change

Walk this list and fix anything that stopped being true:

- [ ] Feature bullets
- [ ] Quick start commands and platform table
- [ ] Supported setups (OS, transports, tested devices, requirements)
- [ ] Good to know / limitations
- [ ] Documentation table and links
- [ ] Length: if a section grows past a screen, move detail to `docs/`

Renaming or moving a doc means updating every link in the same commit — no redirects exist.

## Verify

```bash
# No stale names or old anchor style in user docs and installers
grep -rn "Installation.md\|README.md#\|'Edge Switch' in README" \
  --include="*.md" --include="*.sh" --include="*.command" --include="*.ps1" --include="*.bat" \
  README.md docs scripts config.example.yaml

# All relative links resolve
python - <<'PY'
import pathlib, re
for md in [pathlib.Path("README.md"), *pathlib.Path("docs").rglob("*.md")]:
    for target in re.findall(r"\]\(([^)#]+)", md.read_text()):
        if target.startswith(("http:", "https:", "mailto:")):
            continue
        if not (md.parent / target).resolve().exists():
            print(f"{md}: broken link -> {target}")
PY

# Repo gate, even for docs-only changes
pytest && ruff check && ruff format --check
```

Archive check: the release archives bundle `README.md`, `LICENSE.txt`, `config.example.yaml` and the user docs (`docs/*.md` plus `docs/features/*.md`). A relative link to a file outside that set (`docs/architecture/`, `rules.d/`, source files) will work on GitHub but fail in the archive — use an absolute GitHub URL for those.

Also check executable bits if an installer or `.sh` was touched, and update `docs/README.md` whenever a page is added, renamed or removed.
