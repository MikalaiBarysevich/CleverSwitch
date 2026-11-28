---
name: release-notes
description: Generate GitHub release notes for unreleased CleverSwitch tags in the established repo format. Use when the user asks to write, draft, prepare, or generate release notes / a release description for CleverSwitch versions.
---

# CleverSwitch Release Notes

Produce a single combined release-notes markdown body covering every unreleased tag, in the repo's current release-notes format. Prior releases at https://github.com/MikalaiBarysevich/CleverSwitch/releases are the reference for tone and bullet style.

## Rules

- **One release, not many.** If multiple unreleased tags exist (e.g. `v1.2.1` and `v1.2.2`), combine all their changes into a single release-notes body (the release will be cut against the latest tag). Never produce one block per intermediate tag.
- **Skip already-published tags.** Check `gh release list` and exclude any tag that already has a published (non-draft) release.
- **Output a single fenced ```markdown code block** containing the raw markdown — no surrounding commentary, no extra prose, ready to paste into the GitHub release editor.
- **Do not invent changes.** Every bullet must trace back to a real commit/PR in the version range. If a PR has no body, infer the change from the diff (`git show --stat <sha>` + targeted `git show <sha> -- <path>`).
- **Checksums are mandatory.** Include a `### Checksums` section with the full SHA-256 of every release asset. Take the values from the draft release's asset digests (`gh release view <tag> --json assets`) when a draft release exists; otherwise leave the `<sha256>` placeholders. Never invent, abbreviate or truncate them. GitHub already shows each asset's digest, but the release body must repeat the full values.
- **State the Windows signing status.** The Windows install bullet must say whether `cleverswitch.exe` is code-signed. It is currently unsigned, so warn that SmartScreen may show an unrecognised-publisher prompt and point users to the checksums.

## Steps

### 1. Find the version range

```bash
git tag -l | sort -V                                                # all tags
gh release list --repo MikalaiBarysevich/CleverSwitch --limit 20    # which are published
```

The range is `<latest published tag>..<latest tag>`. Tags inside that range are the unreleased ones to document.

### 2. Extract the format from a recent release

```bash
gh release view <recent-published-tag> --repo MikalaiBarysevich/CleverSwitch
```

Use the most recent published release for tone and bullet style, but the structure in Step 4 is authoritative — older releases still contain a Platform Support section and the old `Installation.md` path.

### 3. Gather commits and PR context

```bash
git log <prev-tag>..<new-tag> --oneline           # for each unreleased version
gh pr view <num> --repo MikalaiBarysevich/CleverSwitch    # for each PR referenced in commits
git show <sha> --stat                                       # what files changed
git show <sha> -- <path>                                    # actual diff when PR body is empty
```

Trivial sync/merge commits with no user-facing impact (e.g. "Sync main") are omitted.

### 4. Write the body

Required structure (keep verbatim except for the Overview/Changes content):

```markdown
### Overview

<one short paragraph: what the release accomplishes from the user's perspective>

### Changes

* **<Short title>:** <what changed and the user-facing impact. Include the technical mechanism only when it explains why the fix matters (e.g. "the `::` form was being parsed as a label and breaking variable expansion").>
* ...

### Installation & Assets

* **Windows:** download `cleverswitch_windows_x64.zip` from the **Assets** section below and follow `docs/installation.md` in the archive. The executable is not code-signed, so SmartScreen may warn about an unrecognised publisher; verify the SHA-256 below before running it.
* **Linux (Arch-based):** `yay -S cleverswitch` (or `paru -S cleverswitch`), then `systemctl --user enable --now cleverswitch.service`. For other distributions, download `cleverswitch_linux.tar.gz` from the **Assets** section below and follow `docs/installation.md` in the archive.
* **macOS:** `brew tap mikalaibarysevich/cleverswitch`, `brew trust mikalaibarysevich/cleverswitch`, `brew install cleverswitch`, then `brew services start cleverswitch`. Or download `cleverswitch_macOS.tar.gz` from the **Assets** section below and follow `docs/installation.md` in the archive.

### Checksums

SHA-256 for the release assets (these match the digest GitHub reports for each asset):

* `cleverswitch_windows_x64.zip` — `<sha256>`
* `cleverswitch_linux.tar.gz` — `<sha256>`
* `cleverswitch_macOS.tar.gz` — `<sha256>`
```

Fill the checksum placeholders from the draft release's asset digests before publishing. If no draft release exists yet, leave the placeholders in the draft body — never invent hashes, and never publish the placeholders.

### 5. Style notes

- Bullet form: `* **Title:** description.` — always bold the leading title, always end with a period.
- Code identifiers (file names, class names, flags, byte values) go in backticks: `setup_startup_windows.bat`, `KEY_FLAG_ANALYTICS`, `0x00`.
- Order bullets by user-visible importance, not by merge order.
- Overview is one paragraph, two sentences max — name the headline change first.
- Never mention PR numbers, commit SHAs, or internal refactors that have no user impact.
- No `Platform Support` section — the README owns the platform/support matrix.
- Installation bullets lead with the package manager (Homebrew, AUR) and fall back to the archive.
- The archive keeps `README.md` at its root and bundles user docs under `docs/`; always link `docs/installation.md`, never `Installation.md`.