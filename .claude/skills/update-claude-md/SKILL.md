---
name: update-claude-md
description: Analyze all changes in the current git branch and update CLAUDE.md if architectural or important changes warrant it. Use this skill when the user asks to update CLAUDE.md, sync docs with branch changes, review what changed architecturally, or before creating a PR to ensure documentation is current. Also trigger when the user says things like "update docs for this branch", "does CLAUDE.md need updating", or "what architectural changes did we make".
disable-model-invocation: true
---

# Update CLAUDE.md from Branch Changes

Analyze changes in the current branch and update CLAUDE.md to reflect any architectural or important changes that Claude needs to know about in future sessions.

## Why this matters

CLAUDE.md is loaded into every conversation. It's the primary way Claude understands project architecture, conventions, and gotchas. When it's stale, Claude makes wrong assumptions. When it's bloated, Claude ignores important rules. The goal is to keep it accurate, concise, and useful.

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

Read the current CLAUDE.md to understand what's already documented.

## Step 2: Classify changes

Go through each changed file and classify it. Only the first category needs CLAUDE.md updates:

**Warrants update** — things Claude can't figure out by reading current code:
- New or removed subscribers, topics, event types, or changes to pub-sub wiring
- New config sections, settings, or CLI arguments
- Changes to device lifecycle or setup flow (app_setup.py)
- New platform-specific behavior or guards
- New external dependencies or required CLI tools
- Changed build/test/lint commands or coverage thresholds
- New architectural patterns, conventions, or gotchas
- Changes to how existing systems interact (e.g., subscriber now listens on a different topic)

**Does NOT warrant update** — Claude can infer these from code:
- Implementation details within established patterns
- Bug fixes that don't change architecture
- New fields on dataclasses unless they change behavior flow
- Test additions or changes
- Refactors that preserve existing patterns
- Config parsing changes following the existing pattern

## Step 3: Draft the update

When updating CLAUDE.md, follow these principles:

**Edit existing sections, don't append.** If the subscriber list changed, update it in place. If a config section was removed, delete its mention. Never create a "Recent changes" or changelog section — CLAUDE.md describes current state, not history.

**Remove stale content.** Outdated information actively misleads Claude — it's worse than a gap. If something was removed or changed, delete or rewrite the old description.

**Keep it scannable.** Each line should pass the test: "Would removing this cause Claude to make mistakes?" If not, don't add it. A bloated CLAUDE.md causes Claude to ignore important rules.

**What belongs vs what doesn't:**

| Include | Exclude |
|---------|---------|
| Bash commands Claude can't guess | Anything derivable from reading code |
| Code style rules differing from defaults | Standard language conventions |
| Testing instructions and preferred runners | Detailed API documentation |
| Architectural decisions specific to project | File-by-file codebase descriptions |
| Developer environment quirks | Frequently changing information |
| Common gotchas or non-obvious behaviors | Self-evident practices |

**Match existing tone and structure.** Write in the same style as the current CLAUDE.md — same heading levels, detail level, and formatting.

## Step 4: Present changes before applying

Present a summary to the user before editing:
- What sections will be added, updated, or removed
- Why each change is needed (what mistake would Claude make without it?)
- Any content being removed and the reason

Wait for user approval before making edits.

## Step 5: Verify the result

After editing, re-read the full CLAUDE.md and verify:
- Every line is still accurate
- Nothing is redundant with what Claude can see in code
- The file is still concise and scannable
- Removed content is fully cleaned up (no dangling references)
