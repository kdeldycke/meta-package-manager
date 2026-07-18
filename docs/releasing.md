# {octicon}`rocket` Releasing

## Release pipeline

The release process is automated via reusable workflows from [`kdeldycke/repomatic`](https://github.com/kdeldycke/repomatic). A push to `main` triggers the `release.yaml` workflow, which produces:

- Python source distributions (`.whl`, `.tar.gz`) uploaded to [PyPI](https://pypi.org/project/meta-package-manager/)
- Nuitka-compiled standalone binaries for Linux, macOS, and Windows (x64 and ARM64) attached to [GitHub Releases](https://github.com/kdeldycke/meta-package-manager/releases)
- A [Guix package definition](https://github.com/kdeldycke/meta-package-manager/tree/main/packaging/guix) for GNU Guix
- A [Nix package definition](https://github.com/kdeldycke/meta-package-manager/tree/main/packaging/nix) for NixOS/Nix

All release artifacts are signed with [GitHub Artifact Attestations](https://docs.github.com/en/actions/security-guides/using-artifact-attestations-to-establish-provenance-for-builds) providing [SLSA v1 provenance](https://slsa.dev/spec/v1.0/).

The release PR must be merged via "Rebase and merge" (never squash). See the `repomatic-release` skill for the full mechanics.

## Chocolatey

The Chocolatey package definition is maintained in-tree at `packaging/choco/meta-package-manager/`, but is no longer pushed to the [Chocolatey community repository](https://community.chocolatey.org/packages/meta-package-manager) (see [Impact on Chocolatey](binaries.md#impact-on-chocolatey) for the rejection rationale). The automated `chocolatey` job has been removed from `release.yaml`; only the in-tree nuspec remains, so users can [build and install locally](packaging.md#chocolatey) and the `choco-source` job in `tests-install.yaml` keeps the build instructions exercised.

The package directory name must match the nuspec basename: this is enforced by [Chocolatey-AU's `AUPackage`](https://github.com/chocolatey-community/Chocolatey-AU/blob/develop/src/Private/AUPackage.ps1), which derives the nuspec path from `Split-Path -Leaf $pwd`.

## Guix

`meta-package-manager` and its dependencies are [part of GNU Guix](https://packages.guix.gnu.org/packages/meta-package-manager/) upstream, merged via [guix/guix#8047](https://codeberg.org/guix/guix/pulls/8047) on 2026-06-28. The package definition is also maintained in-tree at `packaging/guix/`. The `guix` job in `release.yaml` runs after the main release, computes the `git-fetch` hash of the tagged checkout (the NAR SHA256 in Nix-style base32, see `packaging/guix/update.py`), and updates the `.scm` file. Since Guix packages live on [Codeberg](https://codeberg.org/guix/guix) and require reviewed PRs, the job only opens a PR to this repository with the updated definition; each version bump is then forwarded upstream as a new Guix PR.

## Nix

The Nix package definition is maintained in-tree at `packaging/nix/` while [NixOS/nixpkgs#506145](https://github.com/NixOS/nixpkgs/pull/506145) is pending review. The `nix` job in `release.yaml` runs after the main release, computes the SRI hash of the GitHub source tarball using `nix-prefetch-url`, and updates `package.nix`. The job opens a PR to this repository with the updated definition, which can then be pushed to the nixpkgs PR branch.

Two dependencies (`click-extra` and `extra-platforms`) are also bundled in `packaging/nix/` since they are not yet in nixpkgs. A `default.nix` wrapper overlays them into the Python package set, and a `flake.nix` provides flake-based access. Once the nixpkgs PR lands, the overlay and bundled dependencies become unnecessary.

## MacPorts and Alpine

The MacPorts Portfile overlay (`packaging/macports/`) and the Alpine APKBUILD overlay (`packaging/alpine/`) have no automated bump job: they pin the released version and its source checksums, and must be refreshed by hand as part of each release. Their build instructions and upstream submission statuses are catalogued on the [packaging page](packaging.md#channels).

## Antivirus false positives on Windows binaries

Moved to the [binaries catalog](binaries.md#antivirus-false-positives-on-windows-binaries), which pairs the engineering background, false-positive playbook, and long-term mitigations with the live per-release detection data.
