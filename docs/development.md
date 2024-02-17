# Development

## Philosophy

1. First create something that works (to provide business value).
1. Then something that’s beautiful (to lower maintenance costs).
1. Finally works on performance (to avoid wasting time on premature
   optimizations).

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

## Setup environment

This **step is required** for all the other sections from this page.

Check out latest development branch:

```shell-session
$ git clone git@github.com:kdeldycke/meta-package-manager.git
$ cd ./meta-package-manager
$ git checkout main
```

Install package in editable mode with all development dependencies:

```shell-session
$ python3 -m pip install poetry
$ poetry install
```

Now you’re ready to hack and abuse `git`.

## Test `mpm` development version

After the steps above, you are free to play with the bleeding edge version of `mpm`:

```shell-session
$ poetry run mpm --version
mpm, version 4.13.0-dev
(...)
```

## Unit-tests

Simply run:

```shell-session
$ poetry run pytest
```

Which should be the same as running non-destructive unit-tests in parallel with:

```shell-session
$ poetry run pytest --numprocesses=auto --skip-destructive ./meta_package_manager/tests
```

````{danger}
If you're not afraid of `mpm` tests messing around with the package managers on your system, you
can run the subset of destructive tests with:

```shell-session
$ poetry run pytest --numprocesses=0 --skip-non-destructive --run-destructive ./meta_package_manager/tests
```

As you can see above we recommend running these tests in (non-deterministic) sequential order as most
package managers don't support concurrency.
````

## Coding style

[Code linting is handled by a workflow](https://github.com/kdeldycke/meta-package-manager/blob/main/.github/workflows/lint.yaml).

## Documentation

The documentation you’re currently reading can be built locally with
[Sphinx](https://www.sphinx-doc.org):

```shell-session
$ poetry run sphinx-build -b html ./docs ./docs/html
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

## Changelog

Before a release, the maintainers will review and rewrite the changelog to make
it clean and readable. Inspiration can be drawn from the
[keep a changelog manifesto](https://keepachangelog.com).

Changes can be inspected by using the comparison URL between the last tagged
version and the `main` branch. This link is available at the top of the
{doc}`/changelog`.

## Release process

All steps of the release process and version management are automated in the
[`changelog.yaml`](https://github.com/kdeldycke/meta-package-manager/blob/main/.github/workflows/changelog.yaml) and
[`release.yaml`](https://github.com/kdeldycke/meta-package-manager/blob/main/.github/workflows/release.yaml) and workflows.

All there's left to do is to:

- [check the open draft prepare-release PR](https://github.com/kdeldycke/meta-package-manager/workflows/pulls?q=is%3Apr+is%3Aopen+head%3Aprepare-release)
  and its changes,
- click the `Ready for review` button,
- click the `Rebase and merge` button,
- let the workflows tag the release and set back the `main` branch into a
  development state.

## Version bump

Versions are bumped to their next `patch` revision during the release process
above by the
[`release.yaml` workflow](https://github.com/kdeldycke/meta-package-manager/blob/main/.github/workflows/release.yaml).

At any point during development, you can bump the version by merging either the
`minor-version-increment` or `major-version-increment` branch, each available
in their own PR.
