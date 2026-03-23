---
name: repomatic-topics
description: Optimize GitHub topics for discoverability by analyzing competition on topic pages.
disable-model-invocation: true
allowed-tools: Bash, Read, Grep, Glob, WebFetch, WebSearch, Task, Edit
argument-hint: '[audit|apply]'
---

## Context

!`grep -A1 '^\[project\]' pyproject.toml 2>/dev/null | tail -1`
!`gh api repos/{owner}/{repo} --jq '.topics | join(", ")' 2>/dev/null || echo "NO_GH_ACCESS"`

## Instructions

You help users optimize their GitHub repository topics (tags) for maximum discoverability, balancing accuracy with competitive positioning on GitHub topic pages.

### Determine repository

- Read `pyproject.toml` for the project name, description, and `keywords` list.
- Use `gh api` to fetch the current GitHub topics from the repo.

### Argument handling

- `audit` (default when `$ARGUMENTS` is empty): Analyze current topics and recommend changes. Do not apply.
- `apply`: Analyze, confirm with the user, then apply via `gh api --method PUT repos/{owner}/{repo}/topics`.

### Analysis process

1. **Inventory features.** Read the codebase (CLI commands, workflows, config options) to understand what the project actually does.

2. **Assess current topics.** For each existing topic, fetch `https://github.com/topics/{topic}` and evaluate:

   - How many repos use the topic.
   - What star count is needed to appear on page 1 (above the fold).
   - Whether this repo can realistically rank there.

3. **Classify competitiveness.** For each topic:

   - **High competition** (page 1 requires 10k+ stars): effectively invisible. Drop unless the topic is core identity.
   - **Medium** (page 1 requires 1k-10k stars): keep only if the repo is borderline viable.
   - **Low/niche** (page 1 requires \<1k stars or few total repos): high ROI — keep or add.

4. **Propose candidate topics.** Search for niche topics where the repo could rank in the top 3. Look for:

   - Feature-specific topics (e.g., `github-labels`, `reusable-workflows`) over generic ones (e.g., `labels`, `ci-cd`).
   - Compound topics that narrow the audience (e.g., `python-automation` vs `automation`).
   - Topics with few repos where claiming them gives instant #1 ranking.

5. **Present recommendations.** Show a table with:

   - Topics to keep (with rank assessment).
   - Topics to drop (with reason: too competitive, inaccurate, etc.).
   - Topics to add (with repo count and expected rank).

GitHub allows up to 20 topics. Fill all 20 slots — unused slots are wasted discoverability.

### After analysis

- Confirm changes with the user before applying.
- When applying, update both GitHub topics (`gh api --method PUT repos/{owner}/{repo}/topics`) and `pyproject.toml` keywords to stay in sync.
- The `pyproject.toml` keywords serve PyPI search — keep them aligned with GitHub topics.

### Next steps

Suggest the user run:

- `/repomatic-lint` to check for any issues introduced.
