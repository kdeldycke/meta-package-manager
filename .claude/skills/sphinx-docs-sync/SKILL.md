---
name: sphinx-docs-sync
description: Two-way comparison and synchronization of Sphinx documentation across sibling projects. Discovers discrepancies in conf.py, install.md, index.md toctree, pyproject.toml docs dependencies, extra-deps sections, readme badges, and static assets. Use when you want to align documentation structure, catch stale dependencies, or push improvements across your Sphinx-enabled repositories.
model: sonnet
disable-model-invocation: true
allowed-tools: Bash, Read, Grep, Glob, Agent
argument-hint: '[path-or-github-url ...]'
---

## Context

!`[ -d docs ] && echo "docs/ exists" || echo "No docs/ directory"`
!`[ -f docs/conf.py ] && head -5 docs/conf.py || echo "No docs/conf.py"`
!`ls ../*/docs/conf.py 2>/dev/null | head -20 || echo "No sibling projects with docs/conf.py"`

## Instructions

You audit Sphinx documentation consistency across sibling projects. Your goal is to find discrepancies in both directions: improvements this project can borrow from siblings, and improvements this project can push to siblings.

### Discover projects

If `$ARGUMENTS` are provided, each argument can be a local directory path or a GitHub repository URL (e.g., `https://github.com/owner/repo` or `owner/repo`). For GitHub URLs, clone the repository into a temporary directory with `gh repo clone`. Otherwise, scan the parent directory of the current working directory for all projects that have a `docs/conf.py` file.

Filter out likely forks: check `git remote get-url origin` and skip projects whose upstream repo name doesn't match the directory name (e.g., a local `click/` pointing to a fork of `pallets/click`). Focus on the user's own projects.

List the discovered projects and confirm with the user before proceeding.

### Collect documentation inventory

For each project, collect (using parallel agents where possible):

#### `docs/conf.py`

Read the full file. Compare every setting, import, and extension list across projects. Look for:

- Extensions or settings present in some projects but missing from others.
- Deprecated or renamed settings. Check the Sphinx and extension changelogs to identify settings that have been renamed, replaced, or are now the default in the installed version and can be removed.
- Stale import patterns (e.g., `tomli` fallback when the minimum Python already ships `tomllib`).
- Missing `encoding` parameters on `read_text()` calls.

#### `docs/index.md`

Compare toctree structure (main and development sections), standard pages (contributing, changelog, code-of-conduct, license), and external links. Toctree entries should use the same ordering and emoji icons across projects.

#### `docs/install.md`

Compare sections across projects: installation method tabs, try-it-now examples, binaries/executables table, shell completion, extra-deps format, dependency graph. Not every section applies to every project (see guidelines).

#### `pyproject.toml` docs dependencies

Compare the `docs` dependency group across projects. Flag missing deps that are imported in `conf.py` but not declared, stale conditional dependencies (e.g., `tomli` when `requires-python` already guarantees `tomllib`), and significant version pin divergence.

#### `readme.md`

Compare badge sets, section structure (quick start, "Used in", "Development"). Flag "Development" sections that should be removed when a `CLAUDE.md` exists.

#### Static assets and auto-generated files

Compare `docs/_static/`, `docs/assets/`, `.rst` API doc files, and any `docs_update.py` scripts. Hunt for stale `.rst` files left over from package renames or previous autodoc runs that reference modules or packages that no longer exist.

### Compare and report

Present findings as tables organized by category. For each discrepancy, indicate:

- **Direction**: borrow from sibling, or push to sibling
- **Severity**: bug fix (stale dep, missing dep), alignment (consistency), or enhancement (new feature)
- **Affected projects**: which repos need the change

Use this format for each category:

```
### Category name

| Issue | Severity | Direction | Projects |
|:------|:---------|:----------|:---------|
| description | bug/align/enhance | borrow/push | list |
```

Group by:

1. Bug fixes (stale deps, missing declared deps, broken links)
2. Structural alignment (toctree, page naming, conf.py settings)
3. Content improvements (install.md sections, extra-deps tables, badges)

### Implement

After presenting the report, ask the user which items to implement. When they confirm, make all the changes, grouping edits by project to minimize context switches.

### Guidelines

- Do NOT change version pins unless the pin is provably stale (e.g., conditional on a Python version that the docs group no longer supports).
- When a dependency appears in multiple groups (main, extras, docs), the version may be intentionally loose in one group because it's constrained transitively. Check `click-extra[sphinx]` and similar meta-extras before flagging loose pins.
- Respect project-specific features: not every project needs every section (e.g., shell completion is only relevant for CLI tools, binaries only for projects with `nuitka.enabled`).
- The list-table format for extra dependencies is only worth using when a project has 3+ extras. For 1-2 extras, keep the simple format.
- Check `[tool.repomatic] nuitka.enabled` before suggesting a binaries section.
- Always verify file existence before recommending changes based on cross-project patterns.
- Flag `pip install` commands that should be `uv tool install` or `uv pip install` per `claude.md` § Prefer `uv` over `pip` in documentation.

### Next steps

Suggest the user run:

- `/repomatic-audit` to check broader workflow and config alignment across the same projects.
- `/repomatic-deps` to analyze dependency graphs for projects with stale or divergent docs deps.
