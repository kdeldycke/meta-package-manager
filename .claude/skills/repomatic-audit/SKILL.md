---
name: repomatic-audit
description: Audit downstream repo alignment with upstream repomatic reference, covering workflows, configs, and conventions.
allowed-tools: Bash, Read, Grep, Glob, WebFetch, Agent
argument-hint: '[all|workflows|configs|claude]'
---

## Context

!`ls .github/workflows/*.yaml 2>/dev/null`
!`grep -h 'uses:.*kdeldycke/repomatic' .github/workflows/*.yaml 2>/dev/null | head -5`
!`grep -A5 '\[tool.repomatic\]' pyproject.toml 2>/dev/null || echo "No [tool.repomatic] section"`
!`[ -f repomatic/__init__.py ] && echo "CANONICAL_REPO" || echo "DOWNSTREAM"`

## Instructions

You perform a comprehensive audit of a downstream repository against the upstream `kdeldycke/repomatic` reference. This goes **beyond** what `repomatic workflow sync` handles — it catches stale action versions in custom job content, missing workarounds, outdated configs, and conventions that can be borrowed from upstream.

**This skill is for downstream repos only.** If the context shows `CANONICAL_REPO`, tell the user this skill is not applicable.

### Scope selection

- `all` (default when `$ARGUMENTS` is empty): Run all audits below.
- `workflows`: Audit workflow files only.
- `configs`: Audit non-workflow config files only.
- `claude`: Audit `claude.md` alignment only.
- `upstream`: Identify downstream innovations that could be contributed back to repomatic.

### Fetching reference files

Use `gh api repos/kdeldycke/repomatic/contents/{path} --jq '.content' | base64 -d` to fetch upstream reference files.

### 1. Workflow audit (`workflows`)

#### Thin-caller workflows

Compare each local thin-caller workflow against its reference. These should be identical (except for files listed in `exclude`). Flag:

- Extra triggers (e.g., spurious `workflow_dispatch`).
- Missing triggers.
- Version pin drift (different `@vX.Y.Z` tag).

#### Header-only workflows (e.g., `tests.yaml`)

The header (name, `on:`, `concurrency:`) is synced automatically, but custom job content is not. Compare the job content against the reference for:

- **Stale action versions**: e.g., `actions/checkout`, `astral-sh/setup-uv`, `codecov/*` — compare pinned versions.
- **Missing workarounds**: e.g., the "Force native ARM64 Python on Windows ARM64" step that sets `UV_PYTHON`.
- **Missing matrix exclusions**: e.g., `windows-11-arm` + Python 3.10 (no native ARM64 build).
- **Outdated integration patterns**: e.g., using `codecov-action` when upstream migrated to `codecov-cli` via `uvx`.
- **Missing pytest output flags**: e.g., `--cov-report=xml`, `--junitxml=junit.xml` needed for codecov-cli.
- **YAML scalar style issues**: e.g., `run: |` where `run: >` is needed for multi-line single commands.

#### Excluded workflows

Respect `exclude` entries from `[tool.repomatic]` in `pyproject.toml`. Report excluded files but do not flag them as drift.

### 2. Config file audit (`configs`)

Compare these files against the upstream reference:

| File | What to check |
|---|---|
| `renovate.json5` | Missing `assignees`, missing package rules, stale binary versions in `postUpgradeTasks` |
| `pyproject.toml` `[tool.typos]` | Missing `default.extend-identifiers` for common capitalizations (GitHub, macOS, PyPI, iOS, etc.) |
| `pyproject.toml` `[tool.bumpversion]` | Missing `ignore_missing_files` |
| `pyproject.toml` `[tool.ruff]` | Missing or divergent lint rules, preview settings |
| `pyproject.toml` `[tool.mypy]` | Missing settings compared to reference |
| `.github/ISSUE_TEMPLATE/` | Filename conventions (hyphens, not underscores), missing labels |
| `.github/code-of-conduct.md` | Stale or non-canonical attribution URLs |
| `.github/funding.yml` | Compare with reference |
| `.gitignore` | Compare with reference |
| `lychee.toml` | Note differences (usually project-specific, just flag for review) |

Skip files that are intentionally excluded via `exclude` in `[tool.repomatic]`.

### 3. `claude.md` audit (`claude`)

Fetch the upstream `claude.md` and identify universally applicable sections that the local `claude.md` is missing. Focus on:

- Terminology and spelling rules.
- Version formatting conventions.
- Modern typing practices.
- Python version compatibility caveats.
- Testing guidelines (e.g., "no test classes" rule).
- Common maintenance pitfalls.
- Command-line option conventions.

Do **not** flag upstream sections that are project-specific (e.g., CLI abstractions, workflow design, release checklists, agent conventions).

### 4. Upstream contribution opportunities (`upstream`)

Scan the downstream repo for patterns, workarounds, or configurations that are **better** than or **missing from** the upstream reference. These are candidates for contributing back to `kdeldycke/repomatic`. Look for:

- **Broader test matrices**: e.g., more OS variants, extra Python versions, additional architecture coverage that upstream could adopt as defaults.
- **Workarounds for known issues**: Steps or configs that fix CI failures or edge cases that upstream hasn't addressed yet.
- **Better tool configurations**: e.g., ruff `extend-include` patterns, pytest addopts, coverage settings that are more complete than upstream.
- **Useful `pyproject.toml` patterns**: e.g., dependency group definitions, build config, or tool settings that could be generalized.
- **Custom workflow steps**: Reusable patterns in header-only workflows (e.g., package install verification, environment variable passing) that could become part of the reference workflow.
- **Documentation improvements**: `claude.md` sections, issue templates, or repo metadata patterns that would benefit all downstream repos.

For each candidate, assess:

1. **Generalizability**: Would this benefit most downstream repos, or is it project-specific?
2. **Complexity**: Is it a simple config change or a significant workflow redesign?
3. **Action**: Suggest filing as a GitHub issue or PR at `kdeldycke/repomatic`, with a draft title and description.

### Output format

For each audit area, produce:

1. A summary table: item, status (MATCH / DRIFT / MISSING / N/A), brief description.
2. For each issue: what the current state is, what the reference has, and the recommended fix.
3. Prioritize: group by severity (breaking/functional issues first, then consistency, then cosmetic).

### After running

Suggest the user run:

- `/repomatic-sync` to fix thin-caller workflow drift automatically.
- Manual edits for header-only workflow drift and config changes.
- `/repomatic-lint` to validate after fixes are applied.
