---
name: repomatic-sync
description: Run workflow sync locally to preview or apply upstream changes before CI does.
model: haiku
disable-model-invocation: true
allowed-tools: Bash, Read, Grep, Glob
argument-hint: '[args]'
---

## Context

!`ls .github/workflows/*.yaml 2>/dev/null`
!`grep -h 'uses:.*kdeldycke/repomatic' .github/workflows/*.yaml 2>/dev/null | head -10`
!`grep -A5 '\[tool.repomatic\]' pyproject.toml 2>/dev/null || echo "No [tool.repomatic] section"`
!`[ -f repomatic/__init__.py ] && echo "CANONICAL_REPO" || echo "DOWNSTREAM"`

## Instructions

You run `repomatic workflow sync` locally — the same command that the `autofix.yaml` workflow's `sync-repomatic` job runs automatically on every push to `main`.

This skill is a **mechanical convenience** for previewing or applying sync changes before pushing. For deeper analysis of what the sync cannot fix (stale action versions in custom job content, missing workarounds, config drift), use `/repomatic-audit`.

### Determine invocation method

- If the context above shows `CANONICAL_REPO`, use `uv run repomatic`.
- Otherwise, use `uvx -- repomatic`.

### Argument handling

- Pass `$ARGUMENTS` through to `<cmd> workflow sync $ARGUMENTS`.
- If `$ARGUMENTS` is empty, run `<cmd> workflow sync` with no extra arguments.

### After running

- Show the diff of changed files.
- Report any files excluded via `exclude` in `[tool.repomatic]`.
- Warn about any breaking changes (removed inputs, renamed jobs, changed defaults).

### Next steps

Suggest the user run:

- `/repomatic-audit workflows` for analysis of drift that sync cannot fix (header-only job content, stale versions).
- `/repomatic-lint workflows` to validate the synced workflow files.
