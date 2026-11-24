---
name: update-agents-md
description: Analyze all changes in the current git branch and update AGENTS.md and the matching file under docs/architecture/ when architectural or important changes warrant it. Use when the user asks to update AGENTS.md, sync docs with branch changes, review what changed architecturally, or before creating a PR to keep documentation current. Also trigger on "update docs for this branch", "does AGENTS.md need updating", or "what architectural changes did we make".
disable-model-invocation: true
---

# Update the agent docs from branch changes

Analyze the changes in the current branch and update the project documentation that agents load: `AGENTS.md` for rules and entry points, and `docs/architecture/<subsystem>.md` for the detail behind them.

## Why this matters

`AGENTS.md` is loaded into every session by every harness. It has to stay short: it carries the rules, commands and the map of where everything else lives. The architectural detail lives in `docs/architecture/` and is read only when a task touches that subsystem. When either is stale, an agent makes wrong assumptions; when `AGENTS.md` grows, agents start ignoring it. The goal is accuracy at the entry point and depth on demand.

## Step 1: Detect the parent branch and gather changes

Find the parent branch — the branch the current one was forked from. Walk the first-parent history looking for the first commit that belongs to another local branch:

```bash
current=$(git rev-parse --abbrev-ref HEAD)

# Walk first-parent commits, find the first one tagged with another branch name
parent=""
for sha in $(git rev-list --first-parent HEAD); do
  branches=$(git branch --contains "$sha" --format='%(refname:short)' | grep -v "^${current}$" | head -1)
  if [ -n "$branches" ]; then
    parent="$branches"
    break
  fi
done

# Fallback: if nothing found, use main
parent="${parent:-main}"
echo "Parent branch: $parent"
```

Then gather the full scope of changes:

```bash
git diff $parent...HEAD --name-status
git diff $parent...HEAD --stat
git log $parent..HEAD --oneline
git diff $parent...HEAD
```

Read `AGENTS.md` and the subsystem docs named by the changed files.

## Step 2: Classify changes

Go through each changed file and classify it. Only the first category needs documentation updates:

**Warrants update** — things an agent cannot figure out by reading current code:
- New or removed subscribers, topics, event types, or changes to pub-sub wiring
- New config sections, settings, or CLI arguments
- Changes to device lifecycle or setup flow (`app_setup.py`)
- New platform-specific behavior or guards
- New external dependencies or required CLI tools
- Changed build/test/lint commands, hook setup, or coverage thresholds
- New architectural patterns, conventions, or gotchas
- Changes to how existing systems interact (e.g. a subscriber now listens on a different topic)

**Does NOT warrant update** — an agent can infer these from code:
- Implementation details within established patterns
- Bug fixes that don't change architecture
- New fields on dataclasses unless they change behavior flow
- Test additions or changes
- Refactors that preserve existing patterns
- Config parsing changes following the existing pattern

## Step 3: Pick the target file

- **`AGENTS.md`** — a rule an agent must follow anywhere in the repo, a command, a convention, a dependency, or a change to the "Where to look" map. Keep it under roughly 150 lines; if a paragraph explains *how a subsystem works*, it belongs in a doc.
- **`docs/architecture/<subsystem>.md`** — mechanism, lifecycle, event flow, retry rules, threading. Match the change to an existing doc:

| Subsystem | Doc |
|---|---|
| Topics, subscribers, threading | `docs/architecture/pub-sub.md` |
| Discovery, hotplug, DeviceLink, channels, receiver arming | `docs/architecture/device-lifecycle.md` |
| InfoTask, discovery retries, sw_id allocation | `docs/architecture/info-tasks.md` |
| macOS BLE/GATT transport | `docs/architecture/macos-ble.md` |
| Edge switch backends and detector | `docs/architecture/edge-switch.md` |
| Logging, config, instance lock | `docs/architecture/logging.md` |
| LogiDevice state and device cache | `docs/architecture/device-model.md` |
| Subscriber wiring | `docs/architecture/wiring.md` |

A genuinely new subsystem gets a new doc under `docs/architecture/` **and** a new row in the `AGENTS.md` table.

## Step 4: Draft the update

**Edit existing sections, don't append.** If the subscriber list changed, update it in place. If a config section was removed, delete its mention. Never create a "Recent changes" or changelog section — these docs describe current state, not history.

**Remove stale content.** Outdated information actively misleads — it is worse than a gap. If something was removed or changed, delete or rewrite the old description.

**Keep it scannable.** Each line should pass the test: "Would removing this cause an agent to make a mistake?" If not, don't add it. A bloated `AGENTS.md` causes agents to ignore important rules.

**What belongs vs what doesn't:**

| Include | Exclude |
|---------|---------|
| Commands an agent can't guess | Anything derivable from reading code |
| Code style rules differing from defaults | Standard language conventions |
| Testing instructions and preferred runners | Detailed API documentation |
| Architectural decisions specific to the project | File-by-file codebase descriptions |
| Developer environment quirks | Frequently changing information |
| Common gotchas or non-obvious behaviors | Self-evident practices |

**Match existing tone and structure.** Write in the same style as the current files — same heading levels, detail level, and formatting.

## Step 5: Present changes before applying

Present a summary to the user before editing:
- Which file each change goes to (`AGENTS.md` or a specific doc)
- Why each change is needed (what mistake would an agent make without it?)
- Any content being removed and the reason

Wait for user approval before making edits.

## Step 6: Verify the result

After editing, verify:
- Every line is still accurate
- Nothing is redundant with what an agent can see in code
- `AGENTS.md` is still concise, and every doc path in its table resolves
- Removed content is fully cleaned up (no dangling references or links)
- `.agents/skills/*/SKILL.md` still describes the current code (topics, constructors, helpers)
