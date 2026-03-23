---
name: repomatic-lint
description: Lint workflows and repository metadata, then explain issues and suggest fixes.
disable-model-invocation: true
allowed-tools: Bash, Read, Grep, Glob
argument-hint: '[workflows|repo|all]'
---

## Context

!`ls .github/workflows/*.yaml 2>/dev/null`
!`[ -f repomatic/__init__.py ] && echo "CANONICAL_REPO" || echo "DOWNSTREAM"`

## Instructions

You help users lint their workflows and repository metadata for common issues.

### Mechanical layer

The `lint.yaml` workflow already runs linting in CI on every push and PR (`lint-repo`, `lint-types`, `lint-yaml`, `lint-github-actions`, `lint-workflow-security`). This skill is useful when you want to lint **locally** before pushing, or to get **explanations and fix suggestions** that CI logs do not provide.

### Determine invocation method

- If the context above shows `CANONICAL_REPO`, use `uv run repomatic`.
- Otherwise, use `uvx -- repomatic`.

### Argument handling

- `all` (default when `$ARGUMENTS` is empty): Run both workflow and repo linting.
- `workflows`: Run `<cmd> workflow lint` only.
- `repo`: Run `<cmd> lint-repo` only.

### After running — analytical layer

This is where the skill adds value beyond what CI provides:

- Explain each issue found: what the problem is, why it matters, and how to fix it.
- Group issues by severity (errors first, then warnings).
- For workflow issues, reference the specific file and line where possible.
- If issues are caused by upstream drift, suggest `/repomatic-sync` or `/repomatic-audit` instead of manual fixes.

### Next steps

Suggest the user run:

- `/repomatic-sync` if workflow files are outdated or have upstream drift.
- `/repomatic-audit` for a comprehensive alignment check beyond what linting covers.
- `/repomatic-changelog check` before a release to validate the changelog too.
