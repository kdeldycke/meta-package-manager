---
name: repomatic-changelog
description: Draft, validate, consolidate, and fix changelog entries.
disable-model-invocation: true
allowed-tools: Bash, Read, Grep, Glob, Edit, Write
argument-hint: '[add|check|fix|consolidate]'
---

## Context

!`head -40 changelog.md 2>/dev/null || echo "No changelog.md found"`
!`git log --oneline -10 2>/dev/null`
!`[ -f repomatic/__init__.py ] && echo "CANONICAL_REPO" || echo "DOWNSTREAM"`

## Instructions

You help users manage their `changelog.md` file. Follow `CLAUDE.md` § Changelog and readme updates for style rules.

### Mechanical layer

The `lint.yaml` workflow runs `lint-changelog` in CI. The `check` and `fix` subcommands below invoke the same tool locally. The `add` subcommand is purely analytical — it reviews git history and drafts entries, which no CI job does.

### Determine invocation method

- If the context above shows `CANONICAL_REPO`, use `uv run repomatic`.
- Otherwise, use `uvx -- repomatic`.

### Argument handling

- `add` (default when `$ARGUMENTS` is empty): Review recent git commits and draft changelog entries. Place entries under the current unreleased section. Describe **what** changed, not **why**. Keep entries concise and actionable.
- `check`: Run `<cmd> lint-changelog` and report results. Explain each issue found.
- `fix`: Run `<cmd> lint-changelog --fix` and show what was changed.
- `consolidate`: Review the unreleased section and consolidate redundant entries. This is analytical work with no CLI equivalent — read the entries, compare against `git log` since the last release tag, and rewrite. See § Consolidation rules below.

### Consolidation rules

Entries accumulate during development as features are built incrementally. Before release, they need consolidation. The goal is a changelog that reads as a release summary, not a development diary.

1. **Read the full unreleased section** and `git log` since the last release tag.
2. **Merge entries that describe the same feature at different stages.** Multiple bullets about adding tools to a registry, then migrating workflows for those tools, then updating Renovate managers for those tools — that is one feature ("add unified tool runner with 13 managed tools"), not twelve.
3. **Merge entries that describe infrastructure and its usage together.** "Add binary download infrastructure" + "add 5 binary tools" + "migrate 5 workflow steps" = one bullet covering the feature end-to-end.
4. **Keep distinct user-facing changes as separate entries.** A breaking config key change and a new CLI command are separate features even if they landed in the same development cycle.
5. **Preserve specifics that help users upgrade.** Tool names, config key names, and breaking changes should remain explicit — consolidation reduces bullet count, not information density.
6. **Remove implementation details** that don't affect users: internal refactors, helper functions, test additions.
7. **Show the before/after** to the user for approval before writing.

### Style rules

Follow `CLAUDE.md` § Changelog and readme updates (what-not-why, concise entries) and § Version formatting (bare versions in changelog headings, no `v` prefix).

### Next steps

Suggest the user run:

- `/repomatic-release check` to validate the project is ready for release.
- `/repomatic-release prep` to prepare the release PR.
