# Development

## Philosophy

1.  First create something that works (to provide business value).
2.  Then something that’s beautiful (to lower maintenance costs).
3.  Finally works on performance (to avoid wasting time on premature
    optimizations).

## Stability policy

This project more or less follows [Semantic Versioning](https://semver.org/).

Which boils down to the following rules of thumb regarding stability:

- **Patch releases** (`0.x.n` → `0.x.(n+1)` upgrades)

  Are bug-fix only. These releases must not break anything and keep
  backward-compatibility with `0.x.*` and `0.(x-1).*` series.

- **Minor releases** (`0.n.*` → `0.(n+1).0` upgrades)

  Includes any non-bugfix changes. These releases must be backward-compatible
  with any `0.n.*` version but are allowed to drop compatibility with the
  `0.(n-1).*` series and below.

- **Major releases** (`n.*.*` → `(n+1).0.0` upgrades)

  Make no promises about backwards-compability. Any API change requires a new
  major release.

## Build status

| Branch    | {gh}`main <tree/main>`                                                                                                                                                                                                          | {gh}`develop <tree/develop>`                                                                                                                                                                                                          |
|-----------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Unittests | [![Unittests status](https://github.com/kdeldycke/meta-package-manager/actions/workflows/tests.yaml/badge.svg?branch=main)](https://github.com/kdeldycke/meta-package-manager/actions/workflows/tests.yaml?query=branch%3Amain) | [![Unittests status](https://github.com/kdeldycke/meta-package-manager/actions/workflows/tests.yaml/badge.svg?branch=develop)](https://github.com/kdeldycke/meta-package-manager/actions/workflows/tests.yaml?query=branch%3Adevelop) |
| Coverage  | [![Coverage status](https://codecov.io/gh/kdeldycke/meta-package-manager/branch/main/graph/badge.svg)](https://codecov.io/gh/kdeldycke/meta-package-manager/branch/main)                                                        | [![Coverage status](https://codecov.io/gh/kdeldycke/meta-package-manager/branch/develop/graph/badge.svg)](https://codecov.io/gh/kdeldycke/meta-package-manager/branch/develop)                                                        |

## Setup a development environment

This **step is required** for all the other sections from this page.

Check out latest development branch:

``` shell-session
$ git clone git@github.com:kdeldycke/meta-package-manager.git
$ cd ./meta-package-manager
$ git checkout develop
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

Run [black](https://github.com/psf/black) to auto-format Python code:

``` shell-session
$ poetry run black .
```

Then run [Pylint](https://docs.pylint.org) code style checks:

``` shell-session
$ poetry run pylint meta_package_manager
```

## Documentation

The documentation you’re currently reading can be built locally with
[Sphinx](https://www.sphinx-doc.org):

``` shell-session
$ poetry run sphinx-build -b html ./docs ./docs/html
```

To update the auto-generated API documention:

``` shell-session
$ poetry run sphinx-apidoc -f -o ./docs .
```

## Screenshots

Once in a while, the maintainers of the project will refresh screenshots found
in the documentation and the `readme.md` file at the root of project.

To produce clean and fancy terminals screenshots, use either:

- [Graphite Shot](https://graphite-shot.now.sh)
- [Carbon](https://github.com/carbon-app/carbon)
- [CodeKeep](https://codekeep.io/screenshot)

## Changelog

From time to time, especially before a release, the maintainers will review and
rewrite the changelog to make it clean and readable. The idea is to have it
stay in the spirit of the [keep a changelog
manifesto](https://keepachangelog.com).

Most (if not all) changes can be derived by simply comparing the last tagged
release with the `develop` branch:
`https://github.com/kdeldycke/meta-package-manager/compare/vX.X.X...develop`.
This direct link should be available at the top of the {doc}`/changelog`.

## Release process

Check you are starting from a clean `develop` branch:

``` shell-session
$ git checkout develop
```

Revision should already be set to the next version, so we just need to set the
released date in the changelog:

``` shell-session
$ vi ./changelog.md
```

Create a release commit, tag it and merge it back to `main` branch:

``` shell-session
$ git add ./meta_package_manager/__init__.py ./changelog.md
$ git commit -m "Release vX.Y.Z"
$ git tag "vX.Y.Z"
$ git push
$ git push --tags
$ git checkout main
$ git pull
$ git merge "vX.Y.Z"
$ git push
```

The next phases of the release process are automated and should be picked up by
GitHub actions. If not, the next section details the manual deployment process.

## Manual build and deployment

Build packages:

``` shell-session
$ poetry build
```

For a smooth release, you also need to [validate the rendering of package’s
long description on
PyPi](https://packaging.python.org/guides/making-a-pypi-friendly-readme/#validating-restructuredtext-markup),
as well as metadata:

``` shell-session
$ poetry check
$ poetry run twine check ./dist/*
```

Publish packaging to [PyPi](https://pypi.python.org):

``` shell-session
$ poetry publish
```

Update revision with [bump2version](https://github.com/c4urself/bump2version)
and set it back to development state by increasing the `patch` level.

``` shell-session
$ git checkout develop
$ poetry run bumpversion --verbose patch
$ git add ./meta_package_manager/__init__.py ./changelog.md
$ git commit -m "Post release version bump."
$ git push
```

## Version bump

Versions are automatically bumped to their next `patch` revision at release
(see above). In the middle of your development, if the upcoming release is no
longer bug-fix only, or gets really important, feel free to bump to the next
`minor` or `major`:

``` shell-session
$ poetry run bumpversion --verbose minor
$ git add ./meta_package_manager/__init__.py ./changelog.md
$ git commit -m "Next release no longer bug-fix only. Bump revision."
$ git push
```
