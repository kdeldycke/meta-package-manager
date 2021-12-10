# Development

## Philosophy

1.  First create something that works (to provide business value).
2.  Then something that’s beautiful (to lower maintenance costs).
3.  Finally works on performance (to avoid wasting time on premature
    optimizations).

## Stability policy

This project more or less follows [Semantic Versioning](https://semver.org/).

Which boils down to the following rules of thumb regarding stability:

- **Patch releases**: `0.x.n` → `0.x.(n+1)` upgrades

  Are bug-fix only. These releases must not break anything and keep
  backward-compatibility with `0.x.*` and `0.(x-1).*` series.

- **Minor releases**: `0.n.*` → `0.(n+1).0` upgrades

  Includes any non-bugfix changes. These releases must be backward-compatible
  with any `0.n.*` version but are allowed to drop compatibility with the
  `0.(n-1).*` series and below.

- **Major releases**: `n.*.*` → `(n+1).0.0` upgrades

  Make no promises about backwards-compability. Any API change requires a new
  major release.

## Build status

{gh}`main branch <tree/main>`: [![Unittests status](https://github.com/kdeldycke/meta-package-manager/actions/workflows/tests.yaml/badge.svg?branch=main)](https://github.com/kdeldycke/meta-package-manager/actions/workflows/tests.yaml?query=branch%3Amain) [![Coverage status](https://codecov.io/gh/kdeldycke/meta-package-manager/branch/main/graph/badge.svg)](https://codecov.io/gh/kdeldycke/meta-package-manager/branch/main)

## Setup a development environment

This **step is required** for all the other sections from this page.

Check out latest development branch:

``` shell-session
$ git clone git@github.com:kdeldycke/meta-package-manager.git
$ cd ./meta-package-manager
$ git checkout main
```

Install package in editable mode with all development dependencies:

``` shell-session
$ pip install poetry
$ poetry install
```

Now you’re ready to hack and abuse git!

## Unit-tests

Install test dependencies and run unit-tests:

``` shell-session
$ poetry run pytest
```

## Coding style

{gh}`Code linting is handled by a workflow <blob/develop/.github/workflows/lint.yaml>`.

## Documentation

The documentation you’re currently reading can be built locally with
[Sphinx](https://www.sphinx-doc.org):

``` shell-session
$ poetry run sphinx-build -b html ./docs ./docs/html
```

The generation of API documention is
{gh}`covered by a dedicated workflow <blob/develop/.github/workflows/docs.yaml>`.

## Screenshots

Project screenshots found in the documentation and the `readme.md` file
needs to be refreshed by hand once in a while.

To produce clean and fancy terminals screenshots, use either:

- [Graphite Shot](https://graphite-shot.now.sh)
- [Carbon](https://github.com/carbon-app/carbon)
- [CodeKeep](https://codekeep.io/screenshot)

## Changelog

Before a release, the maintainers will review and rewrite the changelog to make
it clean and readable. Inspiration can be drawn from the [keep a changelog
manifesto](https://keepachangelog.com).

Changes can be derived by simply comparing the last tagged release with the
`main` branch:
`https://github.com/kdeldycke/meta-package-manager/compare/vX.X.X...main`.
This direct link should be available at the top of the {doc}`/changelog`.

## Release process

Make sure you are starting from a clean `main` branch:

``` shell-session
$ git checkout main
```

Revision should already be set to the next version, so we just need to prepare
the changelog:

  - Set the released date to today

    ``` shell-session
    $ sed -i "s/(unreleased)/(`date +'%Y-%m-%d'`)/" ./changelog.md
    ```

  - Update the comparison URL (replace `X.X.X` with the version to be released):

    ``` shell-session
    $ sed -i "s/\.\.\.main>/\.\.\.vX.X.X>/" ./changelog.md
    ```

  - Remove the warning message:

    ``` shell-session
    $ sed -i "/^\`\`\`/,/^$/ d" ./changelog.md
    ```

Then create a release commit and tag it:

``` shell-session
$ git add ./changelog.md
$ git commit -m "Release vX.Y.Z"
$ git tag "vX.Y.Z"
$ git push
$ git push --tags
```

The next steps of the release process are automated and should be picked up

## Version bump

Versions are bumped to their next `patch` revision during the release process
above by the {gh}`build workflow <blob/develop/.github/workflows/build.yaml>`.

In the middle of your development, if the upcoming release is no longer bug-fix
only, feel free to bump to the next `minor`:

``` shell-session
$ poetry run bumpversion --verbose minor
$ git add ./meta_package_manager/__init__.py ./changelog.md
$ git commit -m "Next release no longer bug-fix only. Bump revision."
$ git push
```

For really big changes, bump the `major`.