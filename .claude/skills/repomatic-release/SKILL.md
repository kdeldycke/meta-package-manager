---
name: repomatic-release
description: Pre-checks, release preparation, and post-release steps.
disable-model-invocation: true
allowed-tools: Bash, Read, Grep, Glob
argument-hint: '[check|prep|post-release]'
---

## Context

!`grep -m1 'version' pyproject.toml 2>/dev/null`
!`head -5 changelog.md 2>/dev/null`
!`git tag --sort=-v:refname | head -5 2>/dev/null`
!`git status --short 2>/dev/null`
!`[ -f repomatic/__init__.py ] && echo "CANONICAL_REPO" || echo "DOWNSTREAM"`

## Instructions

You help users prepare and validate releases.

### Determine invocation method

- If the context above shows `CANONICAL_REPO`, use `uv run repomatic`.
- Otherwise, use `uvx -- repomatic`.

### Argument handling

- `check` (default when `$ARGUMENTS` is empty): Run pre-flight validation. Check that the working tree is clean, changelog has unreleased entries, version is consistent across files, and lint-changelog passes. Cross-check against § Release checklist below. Report any blockers.
- `prep`: Run `<cmd> release-prep` and show the resulting diff. Explain the freeze/unfreeze commit structure (see § Release PR: freeze and unfreeze commits below). Remind that the release PR must use "Rebase and merge", never squash.
- `post-release`: Run `<cmd> release-prep --post-release` and show results.

### After running

- Cross-check against § Release checklist.
- Warn about any incomplete items.
- Explain the version formatting rules: bare versions for package references, `v`-prefixed for tag references (see `CLAUDE.md` § Version formatting).

### Release checklist

A complete release consists of all of the following. If any are missing, the release is incomplete:

- **Git tag** (`vX.Y.Z`) created on the freeze commit.
- **GitHub release** with non-empty release notes matching the `changelog.md` entry for that version.
- **Binaries attached** to the GitHub release for all 6 platform/architecture combinations (linux-arm64, linux-x64, macos-arm64, macos-x64, windows-arm64, windows-x64).
- **PyPI package** published at the matching version.
- **`changelog.md`** entry with the release date and comparison URL finalized.

### Release workflow design

The release process uses defensive workflow design. See `CLAUDE.md` § Defensive workflow design for the general principle (belt-and-suspenders). The subsections below document release-specific implementation rationale.

#### `workflow_run` checkout pitfall

See also: [actions/checkout#504](https://github.com/actions/checkout/issues/504) for context on `actions/checkout`'s default merge commit behavior on pull requests.

When `workflow_run` fires, `github.event.workflow_run.head_sha` points to the commit that *triggered* the upstream workflow — not the latest commit on `main`. If the release cycle added commits after that trigger (freeze + unfreeze), checking out `head_sha` produces a stale tree and the resulting PR will conflict with current `main`.

**Fix:** Use `github.sha` instead, which for `workflow_run` events resolves to the latest commit on the default branch. The `workflow_run` trigger's purpose is *timing* (ensuring tags exist), not pinning to a specific commit. This applies to any job that needs the current state of `main` after an upstream workflow completes.

#### Immutable releases

The release workflow creates a draft, uploads all assets, then publishes. Once published with [GitHub immutable releases](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases) enabled, tags and assets are locked. Tag names are permanently burned — reinforcing the skip-and-move-forward principle (see `CLAUDE.md` § Skip and move forward). Release notes remain editable for `sync-github-releases`.

**What immutable releases actually locks:** Immutability only blocks **asset uploads and modifications** on published releases (`HTTP 422: Cannot upload assets to an immutable release`). Published releases can still be **deleted** (along with their tags via `--cleanup-tag`). This distinction is critical for the dev release strategy below.

**Dev releases use drafts.** The `sync-dev-release` job creates dev pre-releases as **drafts** (`--draft --prerelease`) rather than published pre-releases. This ensures the workflow can upload binaries and packages to the release after creation. The release stays as a draft permanently — it is never published. On the next push, `cleanup_dev_releases()` deletes all existing `.dev0` releases (drafts are always deletable) before creating a fresh one. See `repomatic/github/dev_release.py` for implementation.

#### Concurrency implementation

Workflows use two concurrency strategies depending on whether they perform critical release operations. Read the `concurrency:` block in each workflow file for the exact YAML. For user-facing documentation, see `readme.md` § Concurrency and cancellation.

**`release.yaml` — SHA-based unique groups.** `release.yaml` handles tagging, PyPI publishing, and GitHub release creation. These operations must run to completion. Using conditional `cancel-in-progress: false` doesn't work because it's evaluated on the *new* workflow, not the old one. If a regular commit is pushed while a release workflow is running, the new workflow would cancel the release because they share the same concurrency group. The solution is to give each release run its own unique group using the commit SHA. Both `[changelog] Release` and `[changelog] Post-release` patterns must be matched because when a release is pushed, the event contains **two commits bundled together** and `github.event.head_commit` refers to the most recent one (the post-release bump).

**`changelog.yaml` — event-scoped groups.** `changelog.yaml` includes `github.event_name` in its concurrency group to prevent cross-event cancellation. This is required because `changelog.yaml` has both `push` and `workflow_run` triggers. Without `event_name` in the group, the `workflow_run` event (which fires when "Build & release" completes) would cancel the `push` event's `prepare-release` job, but then skip `prepare-release` itself (due to `if: github.event_name != 'workflow_run'`), so `prepare-release` would never run.

#### Release PR: freeze and unfreeze commits

The `prepare-release` job in `changelog.yaml` creates a PR with exactly **two commits** that must be merged via "Rebase and merge" (never squash):

1. **Freeze commit** (`[changelog] Release vX.Y.Z`) — Freezes everything to the release version: finalizes the changelog date and comparison URL, removes the "unreleased" warning, freezes workflow action references to `@vX.Y.Z`, and freezes CLI invocations to a PyPI version.
2. **Unfreeze commit** (`[changelog] Post-release bump vX.Y.Z → vX.Y.Z`) — Unfreezes for the next development cycle: reverts action references back to `@main`, reverts CLI invocations back to local source (`--from . repomatic`), adds a new unreleased changelog section, and bumps the version to the next patch.

The auto-tagging job in `release.yaml` depends on these being **separate commits** — it uses `release_commits_matrix` to identify and tag only the freeze commit. Squashing would merge both into one, breaking the tagging logic.

**Squash merge safeguard:** The `detect-squash-merge` job in `release.yaml` detects squash merges by checking if the head commit message starts with `` Release `v `` (the PR title pattern) rather than `[changelog] Release v` (the canonical freeze commit pattern). When detected, it opens a GitHub issue assigned to the person who merged, then fails the workflow. The release is effectively skipped — existing safeguards in `create-tag` prevent tagging, publishing, and releasing.

On `main`, workflows use `--from . repomatic` to run the CLI from local source (dogfooding). The freeze commit freezes these to `'repomatic==X.Y.Z'` so tagged releases reference a published package. The unfreeze commit reverts them back for the next development cycle.

### Next steps

Suggest the user run:

- `/repomatic-changelog consolidate` to clean up changelog entries before release.
- `/repomatic-changelog check` to verify the changelog is consistent.
- `/repomatic-release post-release` after the release PR is merged (if using `prep`).
