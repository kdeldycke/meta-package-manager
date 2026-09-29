# {octicon}`git-pull-request` Contribution guide

Candidates for a new package manager come from `mpm`'s own coverage map. The {doc}`/benchmark` holds one row per tool any comparable wrapper drives, so a blank cell in its `mpm` column marks a tool nobody has assessed yet: that is the worklist. {doc}`/unsupported` is the other half of the map, recording each tool already declined and the reason, which is worth checking before proposing one.

## Document a new package manager

Not a coder? No problem.

You can still provide invaluable information. [Open a new issue](https://github.com/kdeldycke/meta-package-manager/issues/new/choose) and fill in the form with raw output of CLI calls to your manager. Armed with this critical data, a contributor or maintainer can attempt a blind implementation. From there we'll collectively iterate until we reach a usable level.

This is often the best approach, as it is sometimes hard to create the same environment as the users.

## Code support for a new package manager

If you’re a Python developer, see the {doc}`/add-new-manager` guide for the full implementation checklist: module structure, registration, testing, and documentation updates.

## Development environment

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
$ uv sync --all-extras --all-groups
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
$ uv sync --group test
$ uv run -- pytest
```

Which should be the same as running non-destructive unit-tests in parallel with:

```shell-session
$ uv run pytest --numprocesses=auto --skip-destructive
```

Destructive tests mess with the package managers on your system. The safe local invocation runs them sequentially:

```shell-session
$ uv run pytest --numprocesses=0 --skip-non-destructive --run-destructive
```

The sequential command cannot interleave `sudo` prompts and spares a workstation the parallel load. CI runs the destructive tests in parallel instead, one scheduling group per backend lock: {mod}`tests.destructive_plan` and the collection hook of {mod}`tests.conftest` hold the details.

### Type checking

The `typing` group carries the stub packages alone, so mypy itself rides along as an overlay:

```shell-session
$ uv run --with mypy --group typing mypy meta_package_manager
```

### Documentation

Build Sphinx documentation locally:

```shell-session
$ uv sync --group docs
$ uv run -- sphinx-build -b html ./docs ./docs/html
```

The `docs` group resolves on Python `3.14` and above. A venv built on an older interpreter resolves the group to nothing, so `sphinx-build` is absent rather than broken: see the comment on `dependency-groups.docs` in the `[tool.uv]` section of `pyproject.toml`.

Add `--fresh-env` after an edit to a generator of `meta_package_manager/_docs.py`, to a manager docstring or to `changelog.md`: an incremental build renders the previous output otherwise.

The generation of API documentation is [covered by a dedicated workflow](https://github.com/kdeldycke/meta-package-manager/blob/main/.github/workflows/docs.yaml).

## Stability policy

This project more or less follows [Semantic Versioning](https://semver.org/).

Which boils down to the following these rules of thumb regarding stability:

- **Patch releases**: `0.x.n` → `0.x.(n+1)` upgrades

  Are bug-fix only. These releases must not break anything and keep backward-compatibility with `0.x.*` and `0.(x-1).*` series.

- **Minor releases**: `0.n.*` → `0.(n+1).0` upgrades

  Includes any non-bugfix changes. These releases must be backward-compatible with any `0.n.*` version but are allowed to drop compatibility with the `0.(n-1).*` series and below.

- **Major releases**: `n.*.*` → `(n+1).0.0` upgrades

  Make no promises about backwards-compatibility. Any API change requires a new major release.

- **Unmaintained managers**: managers whose `unmaintained` flag is set

  Are exempt from the rules above. An unmaintained manager may be removed, in part or in full, in any release and without notice, once keeping it working becomes too burdensome. It is hidden from the default selection and kept out of the test matrices. The criteria for the flag are those of the {attr}`~meta_package_manager.manager.PackageManager.unmaintained` attribute, and each flagged manager states its evidence on its own page.

## `claude.md` file

```{include} ../claude.md
:start-line: 2
```
