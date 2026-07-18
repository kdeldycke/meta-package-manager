# {octicon}`package` Add a packaging channel

A *channel* is a route by which users install `mpm`: a Linux distribution's package manager, a language package manager, or a cross-distribution installer. The [packaging page](packaging.md) catalogs the ones already wired up. This page is the playbook for adding another.

Channels come in two shapes:

- **Spec-based**: a build recipe lives in the repository under `packaging/{channel}/`, CI builds and installs from it, and it is usually submitted upstream to the distribution. This is the full procedure below.
- **Released-artifact only** (PyPI, Homebrew, Scoop, GitHub Releases, Stew, ZeroBrew): no in-repo recipe, just an install method plus a scheduled job that tests the published artifact. For these, only steps 4 and 5 apply, and the test job runs on a schedule rather than every push (see the `schedule` trigger and the *Schedule-only workflows* rule).

## 1. Learn the target's conventions

Read the target's packaging format, contribution guide, and commit and style rules before writing anything. Prefer the project's own in-repo documentation (its `README`, coding-style and commit-style files, and a handful of recently merged packages) over its wiki: wikis are frequently stale or behind anti-bot walls. For Alpine, `wiki.alpinelinux.org` was unreachable, and the canonical rules were in the `aports` repo's `README.md`, `CODINGSTYLE.md`, and `COMMITSTYLE.md`.

Note two things that vary by target: where new packages must land (Alpine requires `testing/`; other trees have their own staging area), and the commit granularity (aports wants one commit per package, titled to its own template).

## 2. Map the dependency closure

Find which of `mpm`'s runtime dependencies the target already ships and which are missing: you must package every missing one, not just `mpm`. Chase the closure transitively, since a missing dependency may pull in its own.

[repology.org](https://repology.org)'s API (`/api/v1/project/{name}`) reports availability per distribution without touching the distribution's own web UI. Pin versions from `uv.lock`, and compute source checksums from the artifacts you actually download, not from a lockfile hash (the algorithms differ).

## 3. Write the specs

Write one recipe for `mpm` and one per missing dependency, in the target's format, under `packaging/{channel}/`. Recurring decisions, each backed by a fact on the [packaging page](packaging.md#test-suite):

- **Source tarball.** The PyPI sdist ships no tests. If the build's check phase must run `mpm`'s suite, build from the GitHub tag tarball (`.../archive/v{version}/...`), which carries `tests/`, `docs/`, and the workflow files the docs tests parse. If it only needs an import check, the sdist is fine.
- **Check-phase scope.** Run only the hermetic unit layer; the integration layer drives real package managers and cannot run in a builder. Deselect the repo-maintenance sync test if it asserts against the installed `extra-platforms` release rather than a packaging invariant.
- **Dependencies without tests.** Some dependency sdists ship no tests (import-smoke-test the built wheel instead); some ship tests that need a file ignored (`packageurl`'s spec suite loads a git submodule absent from its sdist).
- **Build backend.** `mpm` and several dependencies build with `uv-build`; confirm the target ships it (Alpine ships it on edge only, which also gates `py3-boltons >= 25`).

Keep the load-bearing comments that explain a non-obvious choice (why the tag tarball, why a test is ignored or deselected) and drop overlay-only chatter that means nothing upstream.

## 4. Add an advisory CI job

Add a `{channel}-source` job to [`tests-install.yaml`](https://github.com/kdeldycke/meta-package-manager/blob/main/.github/workflows/tests-install.yaml) that builds and installs from the in-repo recipe, then runs `mpm --version`. Start it advisory: name it `⁉️ {channel}-source` with `continue-on-error: true`, and promote it to `✅` (dropping `continue-on-error`) only once it has gone green end-to-end, the way `macports-source` and `apk-source` did. Update the workflow's `paths:` filters and its header comment, and add the source-URL comment the *Workflow source URLs* rule requires. Containerized distributions need `runs-on: ubuntu-24.04`: the `ubuntu-slim` image has no Docker.

## 5. Wire the docs

Three files plus the workflow move together (the *Distributor sync* set):

- [`docs/packaging.md`](packaging.md): add a row to the channels table and a build-from-spec section.
- [`docs/install.md`](install.md): add a tab. A released channel gets full instructions; a channel still pending upstream review gets a stub tab (status line, the post-landing one-liner, and a link into its `packaging.md` section), with the build steps living in `packaging.md` alone.
- `changelog.md`: one entry naming the channel and its `{channel}-source` job.

## 6. Prepare the upstream submission

Fork the target's repository and branch from its default branch. Then adapt the in-repo recipe to the target's canon: the committed copy is tuned for CI, and the upstream tree has its own rules. For `aports` that meant contributor and maintainer comment headers, dropping a `builddir` that equalled the default, citing the documentation-site URL instead of a repository-internal reference, placing the packages in `testing/`, and one signed commit per package in dependency order following the commit-style template. Push to your fork and open the merge request or pull request titled to the target's convention.

## 7. Monitor upstream CI and iterate

The target's pipeline is the real cross-architecture build-and-test validation you cannot run locally, so watch it through to completion. If the target's web UI is behind authentication or an anti-bot wall, query its forge API instead: for GitLab, `/api/v4/projects/{namespace%2Frepo}/merge_requests/{iid}/pipelines`, and note that the build jobs may run on your *fork's* project, reachable through the parent pipeline's bridges rather than the target project.

Rebase when the tree asks for it: `aports` and many others fast-forward-merge, so a `need_rebase` status is routine and not a conflict. Rebase onto the latest default branch and force-push with lease.

## Maintenance

A spec that pins a released version and its checksums (MacPorts, Alpine) is bumped by hand at each release. The Nix and Guix definitions are bumped automatically by dedicated `release.yaml` jobs. See the [releasing page](releasing.md) for which is which.
