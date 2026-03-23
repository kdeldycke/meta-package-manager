# CLAUDE.md

This file provides guidance to [Claude Code](https://claude.ai/code) when working with code in this repository.

## Project overview

Meta Package Manager (`mpm`) is a CLI that wraps multiple package managers (Homebrew, apt, pip, npm, etc.) behind a unified interface. It can list, search, install, upgrade, and remove packages across all supported managers simultaneously.

## Upstream conventions

This repository uses reusable workflows from [`kdeldycke/repomatic`](https://github.com/kdeldycke/repomatic) and follows the conventions established there. For code style, documentation, testing, and design principles, refer to the upstream `claude.md` as the canonical reference.

**Contributing upstream:** If you spot inefficiencies, improvements, or missing features in the reusable workflows, propose changes via a pull request or issue at [`kdeldycke/repomatic`](https://github.com/kdeldycke/repomatic/issues).

## Philosophy

1. First create something that works (to provide business value).
1. Then something that's beautiful (to lower maintenance costs).
1. Finally works on performance (to avoid wasting time on premature optimizations).

## Stability policy

This project more or less follows [Semantic Versioning](https://semver.org/).

Which boils down to the following these rules of thumb regarding stability:

- **Patch releases**: `0.x.n` → `0.x.(n+1)` upgrades

  Are bug-fix only. These releases must not break anything and keep
  backward-compatibility with `0.x.*` and `0.(x-1).*` series.

- **Minor releases**: `0.n.*` → `0.(n+1).0` upgrades

  Includes any non-bugfix changes. These releases must be backward-compatible
  with any `0.n.*` version but are allowed to drop compatibility with the
  `0.(n-1).*` series and below.

- **Major releases**: `n.*.*` → `(n+1).0.0` upgrades

  Make no promises about backwards-compatibility. Any API change requires a new
  major release.

## Build status

[`main` branch](https://github.com/kdeldycke/meta-package-manager/tree/main):
[![Unittests status](https://github.com/kdeldycke/meta-package-manager/actions/workflows/tests.yaml/badge.svg?branch=main)](https://github.com/kdeldycke/meta-package-manager/actions/workflows/tests.yaml?query=branch%3Amain)
[![Coverage status](https://codecov.io/gh/kdeldycke/meta-package-manager/branch/main/graph/badge.svg)](https://codecov.io/gh/kdeldycke/meta-package-manager/branch/main)

## Commands

### Setup environment

Check out latest development branch:

```shell-session
$ git clone git@github.com:kdeldycke/meta-package-manager.git
$ cd ./meta-package-manager
$ git checkout main
```

Install package in editable mode with all development dependencies:

```shell-session
$ python -m pip install uv
$ uv venv
$ source .venv/bin/activate
$ uv sync --all-extras
```

### Test `mpm` development version

After the steps above, you are free to play with the bleeding edge version of `mpm`:

```shell-session
$ uv run -- mpm --version
(...)
mpm, version 4.13.0
```

### Unit-tests

Run unit-tests with:

```shell-session
$ uv sync --extra test
$ uv run -- pytest
```

Which should be the same as running non-destructive unit-tests in parallel with:

```shell-session
$ uv run pytest --numprocesses=auto --skip-destructive
```

Destructive tests mess with the package managers on your system. Run them sequentially:

```shell-session
$ uv run pytest --numprocesses=0 --skip-non-destructive --run-destructive
```

Sequential order is recommended as most package managers don't support concurrency.

### Documentation

Build Sphinx documentation locally:

```shell-session
$ uv sync --extra docs
$ uv run -- sphinx-build -b html ./docs ./docs/html
```

The generation of API documentation is
[covered by a dedicated workflow](https://github.com/kdeldycke/meta-package-manager/blob/main/.github/workflows/docs.yaml).

## Screenshots

Project screenshots found in the documentation and the `readme.md` file needs
to be refreshed by hand once in a while.

To produce clean and fancy terminals screenshots, use either:

- [Graphite Shot](https://graphite-shot.now.sh)
- [Carbon](https://github.com/carbon-app/carbon)
- [CodeKeep](https://codekeep.io/screenshot)
- [chalk.ist](https://chalk.ist)
