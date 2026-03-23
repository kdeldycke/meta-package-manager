---
name: repomatic-test
description: Run and write YAML test plans for compiled binaries.
disable-model-invocation: true
allowed-tools: Bash, Read, Grep, Glob, Edit, Write
argument-hint: '[--command CMD] [test-plan.yaml]'
---

## Context

!`find . -name '*.yaml' -path '*/test*plan*' -o -name '*.yml' -path '*/test*plan*' 2>/dev/null | head -10`
!`grep -A2 'test.plan' pyproject.toml 2>/dev/null || echo "No test plan config in pyproject.toml"`
!`[ -f repomatic/__init__.py ] && echo "CANONICAL_REPO" || echo "DOWNSTREAM"`

## Instructions

You help users run YAML-based test plans against compiled binaries or write new test plans.

### Determine invocation method

- If the context above shows `CANONICAL_REPO`, use `uv run repomatic`.
- Otherwise, use `uvx -- repomatic`.

### Argument handling

- If `$ARGUMENTS` includes `--command` or a test plan file path, pass through to `<cmd> test-plan $ARGUMENTS`.
- If `$ARGUMENTS` is empty, check for existing test plan files. If found, offer to run them. If none found, offer to help write one.

### On failure

- Read the full trace output and explain what went wrong.
- Identify whether the failure is in the test plan definition, the binary under test, or the test infrastructure.
- Suggest specific fixes.

### Next steps

Suggest the user run:

- `/repomatic-lint` for broader repository validation beyond test plans.
