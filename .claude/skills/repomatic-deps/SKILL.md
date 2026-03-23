---
name: repomatic-deps
description: Generate and analyze dependency graphs from uv lockfiles.
disable-model-invocation: true
allowed-tools: Bash, Read, Grep, Glob
argument-hint: '[--level N] [args]'
---

## Context

!`[ -f uv.lock ] && echo "uv.lock exists" || echo "No uv.lock found"`
!`[ -f repomatic/__init__.py ] && echo "CANONICAL_REPO" || echo "DOWNSTREAM"`

## Instructions

You help users generate and analyze dependency graphs from their uv lockfiles.

### Mechanical layer

The `autofix.yaml` workflow's `update-deps-graph` job already regenerates the dependency graph on every push to `main`. This skill is useful for **interactive analysis** — understanding the graph, spotting concerns, or generating it before pushing.

### Determine invocation method

- If the context above shows `CANONICAL_REPO`, use `uv run repomatic`.
- Otherwise, use `uvx -- repomatic`.

### Argument handling

- Pass `$ARGUMENTS` through to `<cmd> update-deps-graph $ARGUMENTS`.
- If `$ARGUMENTS` is empty, run `<cmd> update-deps-graph` with no extra arguments.

### After running

- Display the Mermaid output.
- Analyze the graph: count total dependencies, flag deep dependency chains, identify packages with high fan-in (many dependents) or fan-out (many dependencies).
- Highlight any notable patterns or potential concerns (e.g., single points of failure, overly deep transitive chains).

### Next steps

Suggest the user run:

- `/repomatic-lint` to check repository metadata for issues.
