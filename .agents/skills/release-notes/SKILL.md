---
name: release-notes
description: Generate GitHub release notes for unreleased CleverSwitch tags in the established repo format. Use when the user asks to write, draft, prepare, or generate release notes / a release description for CleverSwitch versions.
---

# CleverSwitch Release Notes

Produce a single combined release-notes markdown body covering every unreleased tag, in the exact format used by prior releases at https://github.com/MikalaiBarysevich/CleverSwitch/releases.

## Rules

- **One release, not many.** If multiple unreleased tags exist (e.g. `v1.2.1` and `v1.2.2`), combine all their changes into a single release-notes body (the release will be cut against the latest tag). Never produce one block per intermediate tag.
- **Skip already-published tags.** Check `gh release list` and exclude any tag that already has a published (non-draft) release.
- **Output a single fenced ```markdown code block** containing the raw markdown — no surrounding commentary, no extra prose, ready to paste into the GitHub release editor.
- **Do not invent changes.** Every bullet must trace back to a real commit/PR in the version range. If a PR has no body, infer the change from the diff (`git show --stat <sha>` + targeted `git show <sha> -- <path>`).

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

Use the most recent published release as the canonical format template. Match its section structure, heading levels, bullet style, and bold-label convention exactly.

### 3. Gather commits and PR context

```bash
git log <prev-tag>..<new-tag> --oneline           # for each unreleased version
gh pr view <num> --repo MikalaiBarysevich/CleverSwitch    # for each PR referenced in commits
git show <sha> --stat                                       # what files changed
git show <sha> -- <path>                                    # actual diff when PR body is empty
```

Trivial sync/merge commits with no user-facing impact (e.g. "Sync main") are omitted.

### 4. Write the body

Required structure (copied from prior releases — keep verbatim except for the Overview/Changes content):

```markdown
### Overview

<one short paragraph: what the release accomplishes from the user's perspective>

### Changes

* **<Short title>:** <what changed and the user-facing impact. Include the technical mechanism only when it explains why the fix matters (e.g. "the `::` form was being parsed as a label and breaking variable expansion").>
* ...

### Platform Support

* **Windows x64**
* **Linux.**
* **macOS.**

### Installation & Assets

* **Windows:** download `cleverswitch_windows_x64.zip` from the **Assets** section below and follow the `Installation.md` included in the archive.
* **Linux:** download `cleverswitch_linux.tar.gz` from the **Assets** section below and follow the `Installation.md` included in the archive.
* **macOS:** download `cleverswitch_macOS.tar.gz` from the **Assets** section below and follow the `Installation.md` included in the archive.
```

### 5. Style notes

- Bullet form: `* **Title:** description.` — always bold the leading title, always end with a period.
- Code identifiers (file names, class names, flags, byte values) go in backticks: `setup_startup_windows.bat`, `KEY_FLAG_ANALYTICS`, `0x00`.
- Order bullets by user-visible importance, not by merge order.
- Overview is one paragraph, two sentences max — name the headline change first.
- Never mention PR numbers, commit SHAs, or internal refactors that have no user impact.