# CLAUDE.md

This file provides guidance to [Claude Code](https://claude.ai/code) when working with code in this repository.

## Project overview

Meta Package Manager (`mpm`) is a CLI that wraps multiple package managers (Homebrew, apt, pip, npm, etc.) behind a unified interface. It can list, search, install, upgrade, and remove packages across all supported managers simultaneously.

## Upstream conventions

This repository uses reusable workflows from [`kdeldycke/repomatic`](https://github.com/kdeldycke/repomatic) and follows the conventions established there. For code style, documentation, testing, and design principles, refer to the upstream `claude.md` as the canonical reference.

**Contributing upstream:** If you spot inefficiencies, improvements, or missing features in the reusable workflows, propose changes via a pull request or issue at [`kdeldycke/repomatic`](https://github.com/kdeldycke/repomatic/issues).

### Source of truth hierarchy

`CLAUDE.md` defines the rules. The codebase and GitHub (issues, PRs, CI logs) are what you measure against those rules. When they disagree, fix the code to match the rules. If the rules are wrong, fix `CLAUDE.md`.

### Keeping `CLAUDE.md` lean

`CLAUDE.md` must contain only conventions, policies, rationale, and non-obvious rules that Claude cannot discover by reading the codebase. Actively remove:

- **Structural inventories** — project trees, module tables, workflow lists. Claude can discover these via `Glob`/`Read`.
- **Code examples that duplicate source files** — YAML snippets copied from workflows, Python patterns visible in every module. Reference the source file instead.
- **General programming knowledge** — standard Python idioms, well-known library usage, tool descriptions derivable from imports.
- **Implementation details readable from code** — what a function does, what a workflow's concurrency block looks like. Only the *rationale* for non-obvious choices belongs here.

## Philosophy

1. First create something that works (to provide business value).
2. Then something that's beautiful (to lower maintenance costs).
3. Finally works on performance (to avoid wasting time on premature optimizations).

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

- **Deprecated managers**: managers whose `deprecated` flag is set

  Are exempt from the rules above. A deprecated manager may be removed, in part or in
  full, in any release and without notice, once keeping it working becomes too
  burdensome. Each deprecation is documented via the manager's `deprecation_url`, and
  deprecated managers are kept out of the functional test matrices. See the `deprecated`
  attribute in `meta_package_manager/manager.py` for the full policy.

## Build status

[`main` branch](https://github.com/kdeldycke/meta-package-manager/tree/main):
[![Unittests status](https://img.shields.io/github/actions/workflow/status/kdeldycke/meta-package-manager/tests.yaml?branch=main&label=%F0%9F%94%AC%20Tests)](https://github.com/kdeldycke/meta-package-manager/actions/workflows/tests.yaml?query=branch%3Amain)
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

### Note for downstream packagers

The mpm test suite has two layers:

- A **hermetic unit layer** (`test_cooldown`, `test_docs`, `test_docstring_corpus`, `test_help`, `test_managers`, `test_pool`, `test_specifier`, `test_version`) that needs no network, no package managers and no writable `$HOME`. It runs cleanly inside a build sandbox; its only extra build dependency is `pyyaml`, imported by `tests/test_docs.py`.
- An **integration layer** (`tests/test_manager_*.py`, `tests/test_cli*.py`) that drives the ~70 real package managers (`apt`, `brew`, `pip`, `npm`, and more) and the `mpm` CLI end-to-end. These cannot run in a hermetic builder.

As of mpm > `6.6.0`, the integration layer **auto-skips when `$HOME` is `/homeless-shelter`** — the build-sandbox convention shared by Guix and Nix — via `extra_platforms.pytest.skip_guix_build` (wired up in `tests/conftest.py`). Those distributors can therefore run the whole `pytest` suite unmodified: just make `pyyaml` available and **do not override `$HOME`** in the package definition, or the auto-skip stops firing and the integration tests fail.

Builders that keep a writable `$HOME` (Debian buildd, RPM mock, etc.) must either disable the suite (`nocheck`, `doCheck = false`, and similar) or ignore the integration modules with `pytest --ignore-glob='tests/test_manager_*.py' --ignore-glob='tests/test_cli*.py'`.

Running only the `sanity-check` phase (or its equivalent) stays a valid minimal option: it confirms the package imports cleanly and its declared dependencies resolve. Full functional verification of the integration layer is covered by [the project's own GitHub Actions CI](https://github.com/kdeldycke/meta-package-manager/actions), where the package managers are pre-installed.

The `--skip-destructive` and `pytest -m "not destructive"` markers exist for *developer* environments where some package managers are present but mutating them would be undesirable. They do not make the suite hermetic.

### Type checking

```shell-session
$ uv run --group typing mypy meta_package_manager
```

### Documentation

Build Sphinx documentation locally:

```shell-session
$ uv sync --extra docs
$ uv run -- sphinx-build -b html ./docs ./docs/html
```

The generation of API documentation is
[covered by a dedicated workflow](https://github.com/kdeldycke/meta-package-manager/blob/main/.github/workflows/docs.yaml).

## Documentation requirements

### Scope of `CLAUDE.md` vs `readme.md`

- **`CLAUDE.md`**: Contributor and Claude-focused directives — code style, testing guidelines, design principles, and internal development guidance.
- **`readme.md`**: User-facing documentation — installation, usage, and public API.

When adding new content, consider whether it benefits end users (`readme.md`) or contributors/Claude working on the codebase (`CLAUDE.md`).

### Knowledge placement

Each piece of knowledge has one canonical home, chosen by audience. Other locations get a brief pointer ("See `module.py` for rationale.").

| Audience              | Home                      | Content                                           |
| :-------------------- | :------------------------ | :------------------------------------------------ |
| End users             | `readme.md`               | Installation, configuration, usage.               |
| Developers            | Python docstrings         | Design decisions, trade-offs, "why" explanations. |
| Workflow maintainers  | YAML comments             | Brief "what" + pointer to Python code for "why."  |
| Bug reporters         | `.github/ISSUE_TEMPLATE/` | Reproduction steps, version commands.             |
| Contributors / Claude | `CLAUDE.md`               | Conventions, policies, non-obvious rules.         |

**YAML to Python distillation:** When workflow YAML files contain lengthy "why" explanations, migrate the rationale to Python module, class, or constant docstrings (using reST admonitions like `.. note::` and `.. warning::`). Trim the YAML comment to a one-line "what" plus a pointer.

### Changelog and readme updates

Always update documentation when making changes:

- **`changelog.md`**: Add a bullet point describing **what** changed (new features, bug fixes, behavior changes), not **why**. Keep entries concise and actionable. Justifications and rationale belong in documentation or code comments, not in the changelog.
- **`readme.md`**: Update relevant sections when adding/modifying public API, classes, or functions.

### Benchmark page (`docs/benchmark.md`)

The benchmark compares `mpm` against related tools. It mixes one generated table with several hand-maintained ones, and its cells follow strict evidence rules.

**Generated vs hand-maintained.** Only the "Package manager support" table is generated: it renders live at Sphinx build time through the `{python:render}` block in `docs/benchmark.md`, which calls `benchmark_managers_table()` from `docs/docs_update.py`, fed by `docs/benchmark.yaml`; its competitor set is the `BENCHMARK_COMPETITORS` tuple. Every other table (Features, Operations, OS, Distribution, Activity, Popularity, Metadata) is edited by hand. There is no checked-in copy to regenerate or keep in sync: the mpm-column ✅ links (class source-line anchors) are computed at build time, so they never drift from the manager source. `test_benchmark_table_renders` guards the generator against crashes and structural regressions.

**Cell glyphs (benchmark only — `readme.md`'s operation matrix keeps plain `✓`).**

- `✅` — supported. The `mpm` `✅` is always a link: to the manager class's source line in the generated table, to the feature's user documentation in the Features table. A competitor's `✅` is a bare glyph.
- `❌` — not supported, **and only ever written with a link to explicit, verifiable evidence** that the project lacks or rejects the feature: an issue/PR closed not-planned, a maintainer "out of scope" / "won't add" comment, a still-open unaddressed feature request, or an official doc/man-page stating the limitation. **Absence of the feature is never sufficient** — if no citable source exists, leave the cell blank. Verify every URL (`gh issue view`, `gh api`, or WebFetch) and keep the exact supporting quote before committing the link; prefer a precise `#issuecomment-<id>` anchor when a maintainer states the position. This mirrors the "Concurrent multi-PM execution" row.
- `🟡` — coarse/bundled support the competitor cannot invoke in isolation (e.g., topgrade's `--only shell` running every shell-plugin manager at once), also with an evidence link.

**`docs/benchmark.yaml`** has four alphabetically-sorted keys: `managers` (which competitor supports each manager), `homepages` (URLs for non-pool managers only), `coarse_support` (`{manager: {competitor: url}}`), and `refused` (`{manager: {competitor: url}}` for competitors that explicitly declined a manager `mpm` wraps). `test_benchmark_yaml_well_formed` enforces the shape plus the no-orphan and no-conflict invariants (a `(manager, competitor)` pair cannot be in both `managers` and `refused`).

**Scope and competitor set.** Feature/Operation rows cover only capabilities in `mpm`'s domain (cross-manager package operations, output, config, distribution). Do not add rows for a competitor's out-of-domain features (a runtime version manager's shims, task runner, env-var management, per-project version files). Columns are the wrapper peer group (`topgrade`, `pacaptr`, `pacapt`, `sysget`, `whohas`) plus `brew` (its Brewfile is a declarative multi-backend installer); `mise`/`asdf` were removed as out-of-scope version managers, kept only as managers `mpm` wraps in the generated table.

**Auditing competitor cells.** When (re)checking a column, research one competitor project at a time (parallel agents work well); each must verify every URL and quote and report "no evidence → blank" rather than infer a gap from absence.

### Manager augmentations page (`docs/augmentations.md`)

Documents capabilities `mpm` backfills on top of native tools. Two classes: *selective* — only some managers need it (full `upgrade --all`, exact/extended search), shown in the per-manager table — and *universal* — every managed tool gains it (`--dry-run` simulation, cross-scheme version parsing, purl identifiers, uniform sudo). The per-manager table renders live at Sphinx build time through the `{python:render}` block calling `augmentations_table()` from `docs/docs_update.py`, derived from the capability declarations (`upgrade_all_is_synthesized()` and the `search_capabilities` flags in `meta_package_manager/capabilities.py`), so it never drifts from the code. `test_augmentations_table_renders` guards the generator.

## File naming conventions

### Extensions: prefer long form

Use the longest, most explicit file extension available. For YAML, that means `.yaml` (not `.yml`). Apply the same principle to all extensions (e.g., `.html` not `.htm`, `.jpeg` not `.jpg`).

### Filenames: lowercase

Use lowercase filenames everywhere. Avoid shouting-case names like `FUNDING.YML` or `README.MD`.

### GitHub exceptions

GitHub silently ignores certain files unless they use the exact name it expects. These are the known hard constraints where you **cannot** use `.yaml` or lowercase:

| File                     | Required name                       | Why                                               |
| ------------------------ | ----------------------------------- | ------------------------------------------------- |
| Issue form templates     | `.github/ISSUE_TEMPLATE/*.yml`      | `.yaml` is not recognized for issue forms         |
| Issue template config    | `.github/ISSUE_TEMPLATE/config.yml` | `.yaml` not recognized                            |
| Funding config           | `.github/funding.yml`               | Only `.yml` documented; no evidence `.yaml` works |
| Release notes config     | `.github/release.yml`               | Only `.yml` documented                            |
| Issue template directory | `.github/ISSUE_TEMPLATE/`           | Must be uppercase; GitHub ignores lowercase       |
| Code owners              | `CODEOWNERS`                        | Must be uppercase; no extension                   |

Workflows (`.github/workflows/*.yaml`) and action metadata (`action.yaml`) officially support both `.yml` and `.yaml` — use `.yaml`.

## Code style

### Terminology and spelling

Use correct capitalization for proper nouns and trademarked names:

<!-- typos:off -->

- **PyPI** (not ~~PyPi~~) — the Python Package Index. The "I" is capitalized because it stands for "Index". See [PyPI trademark guidelines](https://pypi.org/trademarks/).
- **GitHub** (not ~~Github~~)
- **GitHub Actions** (not ~~Github Actions~~ or ~~GitHub actions~~)
- **JavaScript** (not ~~Javascript~~)
- **TypeScript** (not ~~Typescript~~)
- **macOS** (not ~~MacOS~~ or ~~macos~~)
- **iOS** (not ~~IOS~~ or ~~ios~~)

<!-- typos:on -->

### Version formatting

The version string is always bare (e.g., `1.2.3`). The `v` prefix is a **tag namespace** — it only appears when the reference is to a git tag or something derived from a tag (action ref, comparison URL, commit message). This aligns with PEP 440, PyPI, and semver conventions.

| Context                                | Format            | Example                                        | Rationale                         |
| :------------------------------------- | :---------------- | :--------------------------------------------- | :-------------------------------- |
| Python `__version__`, `pyproject.toml` | `1.2.3`           | `version = "6.1.2"`                            | PEP 440 bare version.             |
| Git tags                               | `` `v1.2.3` ``    | `` `v6.1.2` ``                                 | Tag namespace convention.         |
| GitHub comparison URLs                 | `v1.2.3...v1.2.4` | `compare/v6.1.1...v6.1.2`                      | References tags.                  |
| GitHub action/workflow refs            | `` `@v1.2.3` ``   | `actions/checkout@v6.0.2`                      | References tags.                  |
| Commit messages                        | `v1.2.3`          | `[changelog] Release v6.1.2`                   | References the tag being created. |
| CLI `--version` output                 | `1.2.3`           | `mpm, version 6.1.2`                           | Package version, not a tag.       |
| Changelog headings                     | `` `1.2.3` ``     | `` ## [`6.1.2` (2026-03-04)] ``                | Package version, code-formatted.  |
| PyPI URLs                              | `1.2.3`           | `pypi.org/project/meta-package-manager/6.1.2/` | PyPI uses bare versions.          |

**Rules:**

1. **No `v` prefix on package versions.** Anywhere the version identifies the *package* (PyPI, changelog heading, CLI output, `pyproject.toml`), use the bare version: `1.2.3`.
2. **`v` prefix on tag references.** Anywhere the version identifies a *git tag* (comparison URLs, action refs, commit messages, PR titles), use `v1.2.3`.
3. **Always backtick-escape versions in prose.** Both `v1.2.3` (tag) and `1.2.3` (package) are identifiers, not natural language. In markdown, wrap them in backticks: `` `v1.2.3` ``, `` `1.2.3` ``. In reST docstrings, use double backticks: ``` ``v1.2.3`` ```.
4. **Development versions** follow PEP 440: `1.2.3.dev0` with optional `+{short_sha}` local identifier.

### Comments and docstrings

- All comments in Python files must end with a period.
- Docstrings use reStructuredText format (vanilla style, not Google/NumPy).
- Documentation in `./docs/` uses MyST markdown format where possible. Fallback to reStructuredText if necessary.
- Keep lines within 88 characters in Python files, including docstrings and comments (ruff default). Markdown files have no line-length limit — do not hard-wrap prose in markdown. Each sentence or logical clause should flow as a single long line; let the renderer handle wrapping.
- Titles in markdown use sentence case.
- **Dataclass field docs:** In dataclasses, document fields with attribute docstrings (a string literal immediately after the field declaration), not `:param:` entries in the class docstring. Attribute docstrings are co-located with the field they describe, recognized by Sphinx, and stay in sync when fields are added or reordered. The class docstring should contain only a summary of the class purpose.

### Documenting code decisions

Document design decisions, trade-offs, and non-obvious implementation choices directly in the code using docstring admonitions (reST `.. warning::`, `.. note::`, `.. caution::`), inline comments, and module-level docstrings for constants that need context.

### `__init__.py` files

Keep `__init__.py` files minimal. They are easy to overlook when scanning a codebase, so avoid placing logic, constants, or re-exports in them. Acceptable content: license headers, package docstrings, `from __future__ import annotations`, and `__version__` (standard Python convention for the root package). Anything else belongs in a named module.

### `TYPE_CHECKING` block

Place a module-level `TYPE_CHECKING` block after all imports (including version-dependent conditional imports). Use `TYPE_CHECKING = False` (not `from typing import TYPE_CHECKING`) to avoid importing `typing` at runtime. See existing modules for the canonical pattern.

Only add `TYPE_CHECKING = False` when there is a corresponding `if TYPE_CHECKING:` block. If all type-checking imports are removed, remove the `TYPE_CHECKING = False` assignment too — a bare assignment with no consumer is dead code.

### Modern `typing` practices

Use modern equivalents from `collections.abc` and built-in types instead of `typing` imports. Use `X | Y` instead of `Union` and `X | None` instead of `Optional`. New modules should include `from __future__ import annotations` ([PEP 563](https://peps.python.org/pep-0563/)).

### Minimal inline type annotations

Omit type annotations on local variables, loop variables, and assignments when mypy can infer the type from the right-hand side. Annotations add visual noise without helping the type checker.

**When to annotate:** Add an explicit annotation only when mypy cannot infer the correct type and reports an error — e.g., empty collections that need a specific element type (`items: list[Package] = []`), `None` initializations where the intended type isn't obvious from later usage, or narrowing a union that mypy doesn't resolve on its own.

**Function signatures are unaffected.** Always annotate function parameters and return types — those are part of the public API and cannot be inferred.

### Python 3.10 compatibility

This project supports Python 3.10+. Be aware of syntax features **not** available in Python 3.10:

- **Multi-line f-string expressions (Python 3.12+):** Cannot break an f-string after `{` onto the next line.
- **Exception groups and `except*` (Python 3.11+).**
- **`Self` type hint (Python 3.11+):** Use `from typing_extensions import Self` instead.

### Imports

- Place imports at the top of the file, unless avoiding circular imports. **Never use local imports inside functions** — move them to the module level. Local imports hide dependencies, bypass ruff's import sorting, and make it harder to see what a module depends on.
- **Version-dependent imports** (e.g., `tomllib` fallback for Python 3.10) should be placed **after all normal imports** but **before the `TYPE_CHECKING` block**. This allows ruff to freely sort and organize the normal imports above without interference.

### Workflow file naming

Related workflows share a prefix for visual grouping in the file listing: `tests.yaml` (unit/integration test suite) and `tests-install.yaml` (distributor installability tests). Apply the same pattern when adding new workflow files.

### Workflow source URLs

Each job that tests a third-party distributor must have a comment above it with the precise URL(s) to verify the package's status on that platform. Use the public-facing package page first (e.g., `formulae.brew.sh`), followed by the source definition (e.g., the GitHub-hosted formula `.rb` or manifest `.json`).

### Distributor sync

`docs/install.md` (the "Installation methods" tab-set) and `.github/workflows/tests-install.yaml` must stay in sync. Both files contain cross-reference comments. When adding or removing a distributor, update both.

### Schedule-only workflows

Jobs that test *released* artifacts from external distributors (PyPI, Homebrew, Scoop, etc.) must not run on every push. They test the published version, not the code being pushed, so they belong on a schedule or manual dispatch only.

### Non-interactive CI

When a third-party tool prompts interactively (path selection, asset selection), pre-create its config files and resolve inputs via `gh` or other CLI tools rather than piping stdin. This is more robust across platforms, especially Windows where stdin redirection often fails with "Incorrect function."

### YAML workflows

For single-line commands that fit on one line, use plain inline `run:` without any block scalar indicator:

```yaml
# Preferred for short commands: plain inline.
  - name: Install project
    run: uv --no-progress sync --frozen --all-extras --group test
```

When a command is too long for a single line, use the folded block scalar (`>`) to split it across multiple lines:

```yaml
# Preferred for long commands: folded block scalar joins lines with spaces.
  - name: Unittests
    run: >
      uv --no-progress run --frozen -- pytest
      --cov-report=xml
      --junitxml=junit.xml
```

Use literal block scalar (`|`) only when the command requires preserved newlines (e.g., multi-statement scripts, heredocs):

```yaml
# Use | for multi-statement scripts.
  - name: Install Python
    run: |
      set -e
      uv --no-progress venv --python "${{ matrix.python-version }}"
```

YAML lines may run up to 120 characters (`yamllint` sets `line-length: max: 120`): don't carry Python's 88-character limit over to workflow comments or reflexively wrap them at 80.

### Command-line options

Always prefer long-form options over short-form for readability when invoking commands in workflow files and scripts:

- Use `--output` instead of `-o`.
- Use `--verbose` instead of `-v`.
- Use `--recursive` instead of `-r`.

The same rule applies to every argv `mpm` constructs at runtime: the manager commands built by the manager classes and definitions, and the `sudo` invocations in `meta_package_manager/sudo.py` (`sudo --non-interactive --validate`, not `sudo -n -v`). Long forms make the `--verbosity INFO` command disclosure self-documenting.

### `uv` flags in CI workflows

When invoking `uv` and `uvx` commands in GitHub Actions workflows:

- **`--no-progress`** on all CI commands (uv-level flag, placed before the subcommand). Progress bars render poorly in CI logs.
- **`--frozen`** on `uv run` commands (run-level flag, placed after `run`). The lockfile should be immutable in CI.
- **Flag placement:** `uv --no-progress run --frozen -- command` (not `uv run --no-progress`).
- **Exceptions:** Omit `--frozen` for `uvx` with pinned versions, `uv tool install`, CLI invocability tests, and local development examples.
- **Prefer explicit flags over environment variables** (`UV_NO_PROGRESS`, `UV_FROZEN`). Flags are self-documenting, visible in logs, avoid conflicts (e.g., `UV_FROZEN` vs `--locked`), and align with the long-form option principle.

## CLI output and logging

`mpm` keeps two output channels distinct: the **state** of an operation (printed with `echo`) and **log messages** (`logging`, gated by `--verbosity`).

### Verbosity tiers

The CLI defaults to `WARNING` (inherited from click-extra's `--verbosity` default). Classify every `logging` call into one tier:

- **`WARNING` (default view):** genuine problems only, such as failures with no other on-screen signal, safety notices (cooldown safeguard skipped, a file about to be overwritten, a silent CLI call that may be hiding a `sudo` password prompt), the end-of-run "N managers reported errors" summary, and timeouts. Plus `critical` for fatal conditions. Keep it sparse.
- **`INFO` (narration):** the operational story, like the selection summary, install/dispatch priority, per-manager announcements, discovery (`X has been installed with Y`), capability skips (`X does not implement Y`), "ignoring option ..." no-ops, and every CLI invocation run on the system (the reproducible `$`-prompt line with forced environment variables, so the user can replay by hand what mpm does). Version-detection probes are the exception and stay at `DEBUG`: they are discovery, fired for every candidate manager, and would drown the narration.
- **`DEBUG` (technical):** raw CLI output (streamed live, line by line, the manager ID glued into the level prefix as `debug:<manager_id>:`), version-detection probes, result refiltering, manager-selection parsing, internal data dumps. Raw output stays at `DEBUG` even for mutating operations, deliberately: streaming it at `INFO` was assessed and dropped when issue 1938 closed satisfied without it, since line-pumped output cannot faithfully reproduce raw passthrough (each `\r` progress redraw becomes its own prefixed line) and would swamp the narration tier. If demand appears for watching live output *with* concurrency (`DEBUG` serializes to one worker via `serial_at_debug`), the lever is ready: `run_cli` takes a per-call `output_level`, gated on `_active_operation` in `CLIExecutor.run`.

Heuristic for a new line: if it narrates a decision, a step, or a command run on the system it is `INFO`; a raw mechanism or a command's output is `DEBUG`; something genuinely wrong **and** not already shown by the ✓/✗ trail is `WARNING`. "Your option had no effect here" is `INFO`, not `WARNING`.

A manager-scoped line passes `extra={"label": manager.id}` instead of naming the manager in the message: click-extra's formatter renders the ID glued into the level prefix (`warning:gem: Could not list installed packages.`), matching the streamed CLI output lines and making logs grep-able by manager. Keep the ID in prose only where it is the object of the sentence (`X has been installed with Y`) or names a config artifact (`No [gem] section found.`).

An enum surfaced in any message must render as its bare member name: give it `__str__`/`__format__` returning `self.name`. A functional `Enum("Operations", (...))` otherwise leaks the `Operations.outdated` repr where the message wanted `outdated`.

### Operation state: the ✓/✗ trail

Fan-out operations report state with a per-item `✓`/`✗` trail plus a persistent finisher, printed via `echo` to stderr, never `logging`. `echo` survives the `WARNING` default and is instead gated on an interactive terminal plus `--progress`, so pipes, CI and serialized runs stay clean.

Concurrency is decided by cross-manager *ordering*, not by whether a command mutates state. Three fan-out primitives, all bounded by `--jobs`:

- **Per manager, concurrent** (`meta_package_manager.execution.collect_from_managers`, one result per manager): commands whose work is independent and reported per manager. The read-only queries (`installed`/`outdated`/`search`), the maintenance commands (`sync`/`cleanup`/`upgrade --all`, which pass `report_state=True` since the trail is their only output), and the inventory exporters (`dump`/`backup`, `sbom`, which collect concurrently then assemble in manager order).
- **Per package, concurrent across managers and serial within each** (`meta_package_manager.execution.collect_per_package`, one result per (package, manager)): the ordering-free state changers `remove`, `upgrade <packages>`, `restore`, and the manager-tied specs of `install`. Managers run in parallel; one manager's own packages run one at a time, since a manager cannot safely run two of its own invocations at once (see `SHARED_LOCK_FAMILIES`).
- **Sequential** (`OperationTrail` in `execution.py`): only `install` when a package is left untied to a manager. Such a package needs a priority search (install with the first manager that has it, skip the rest), which is genuinely cross-manager-sequential. `warn_jobs_ignored` notes at `INFO` when an explicit `--jobs` is therefore ignored.

The shared-lock families that make within-family concurrency unsafe (`brew`/`cask` over Homebrew's update lock, `apt`/`apt-mint`/`deb-get` over dpkg, plus the RPM and pacman families) are catalogued in `execution.py`'s `SHARED_LOCK_FAMILIES`. The mutating fan-outs enforce them: `merge_into_lock_lanes` collapses each family into one `dispatch` lane, so its members run serially (one shared backend lock, never raced) while distinct families still run in parallel. The read-only queries take no backend lock and keep one lane per manager. A family lane also shares a command cache (`CLIExecutor.run_cache`), so members resolving to a byte-identical invocation (`brew`/`cask` both running `brew update` for `sync`) run the subprocess once. Adding a newly-conflicting set is a one-line edit: append a `frozenset` of ids to `SHARED_LOCK_FAMILIES`.

Trail conventions:

- Two shapes: **package-keyed** (`✓ foo installed with brew`, for `install`/`remove`/`upgrade <packages>`/`restore`) and **manager-keyed** (`✓ brew`, `✓ Synced N/M managers`, for `sync`/`cleanup`/`upgrade --all`).
- The finisher counts **per (package, manager) attempt**, matching the trail lines: a package acted on by two managers is `2/2`, not `1/1`.
- A `✗` line is TTY-only, so failures also emit a `critical: Could not ...` (shown everywhere) as the durable record and the non-zero-exit rationale. Keep both despite the overlap on a TTY.

### Exit codes

Action commands (`install`, `remove`, `upgrade <packages>`, `restore`) collect per-package failures and exit non-zero with a `critical:` summary. `-0`/`--zero-exit` opts out of that gate (see `exit_on_failures` in `cli.py`): the summary still prints but the exit stays `0`; usage and configuration errors keep exiting `2` regardless. Maintenance commands (`sync`, `cleanup`, `upgrade --all`) are best-effort: they mark a failed manager `✗` but stay exit-`0`.

## Testing guidelines

- Use `@pytest.mark.parametrize` when testing the same logic for multiple inputs. Prefer parametrize over copy-pasted test functions that differ only in their data — it deduplicates test logic, improves readability, and makes it trivial to add new cases.
- Keep test logic simple with straightforward asserts.
- Tests should be sorted logically and alphabetically where applicable.
- Test coverage is tracked with `pytest-cov` and reported to Codecov.
- Do not use classes for grouping tests. Write test functions as top-level module functions. Only use test classes when they provide shared fixtures, setup/teardown methods, or class-level state.
- **`@pytest.mark.once` for run-once tests.** Define a custom `once` marker (in `[tool.pytest].markers`) to tag tests that only need to run once — not across the full CI matrix. Typical candidates: CLI entry point invocability, plugin registration, package metadata checks. The main test matrix filters them out with `pytest -m "not once"`, while a dedicated `once-tests` job runs them on a single runner.
- **CI-only pytest flags belong in workflow steps, not `[tool.pytest].addopts`.** Flags that emit CI-only artifacts (`--cov-report=xml`, `--junitxml=junit.xml`) pollute local runs when placed in `addopts`: keep `addopts` for flags that apply everywhere and pass CI-specific ones in the workflow `run:` step. Coverage settings (`run.branch`, `run.source`, `report.precision`) belong in `[tool.coverage]`, not in `--cov-*` flags.
- **Pass `encoding="UTF-8"` to `subprocess.run(..., text=True)` when output may contain non-ASCII bytes** (emoji in a workflow `name:`, accented author names, translated strings). `text=True` alone decodes with the platform default (`cp1252` on Windows), so such output raises `UnicodeDecodeError` only in Windows CI while passing on macOS and Linux. Test helpers shelling out to package managers or `git` are the usual offenders.
- **TTY-gated output needs a pseudo-terminal to test.** The `✓`/`✗` trail, finishers and spinners only render on an interactive terminal, so click-extra's `CliRunner` (non-TTY) never emits them — drive the CLI under `pty.openpty()` to exercise them. Most CLI tests instead assert on the stdout table, exit code, or an explicit `--verbosity`, none of which are TTY-gated.
- **`--dry-run` simulates read CLIs too.** It dry-runs *every* manager invocation, including the installed-package lookup that `remove`/`upgrade` use to find their source managers — so a dry-run of those reports "not recognized" and cannot exercise their multi-manager path. Reach for purls (which carry the manager and bypass the lookup) or unit fixtures instead.
- **The suite is hermetic with respect to the host `mpm` config.** click-extra's default `--config` search resolves to the host config folder (`~/Library/Application Support/mpm` on macOS, `~/.config/mpm` on Unix). Any `config.toml` there would otherwise leak into every in-process CLI invocation: a local `cpan = false` drops the manager, so `check_manager_selection` assertions expecting the full default set fail locally while passing in CI. The `isolate_user_config` autouse fixture in `tests/conftest.py` repoints config discovery at an empty temp directory, so host config never reaches the suite. Tests that exercise config loading pass `--config <path>` explicitly, which overrides the default and is left unaffected.

## Design principles

### Linting and formatting

Linting and formatting are automated via GitHub workflows. Developers don't need to run these manually during development, but are still expected to do best effort. Push your changes and the workflows will catch any issues and perform the nitpicking.

### Ordering conventions

Keep definitions sorted for readability and to minimize merge conflicts:

- **Workflow jobs**: Ordered by execution dependency (upstream jobs first), then alphabetically within the same dependency level.
- **Python module-level constants and variables**: Alphabetically, unless there is a logical grouping or dependency order. Hard-coded domain constants should be placed at the top of the file, immediately after imports. These constants encode domain assertions and business rules — surfacing them early gives readers an immediate sense of the assumptions the module operates under.
- **YAML configuration keys**: Alphabetically within each mapping level.
- **Documentation lists and tables**: Alphabetically, unless a logical order (e.g., chronological in changelog) takes precedence.

### Prefer `uv` over `pip` in documentation

Documentation and install pages must use `uv` as the default package installer. When showing how to install the package, use `uv tool install` (for CLI tools) or `uv pip install` (for libraries/extras). Alternative installers (`pip`, `pipx`, etc.) may appear as secondary options in tab sets or dedicated sections, but `uv` must be the primary/default command shown.

### Idempotency by default

Workflows and CLI commands must be safe to re-run. Running the same command or workflow twice with the same inputs should produce the same result without errors or unwanted side effects.

**In practice:** use `--skip-existing`, check for existing state before writing, prefer upsert semantics, make file-modifying operations convergent.

### Common maintenance pitfalls

- **Documentation drift** is the most frequent issue. CLI output, version references, and workflow job descriptions in `readme.md` go stale after every release or refactor. Always verify docs against actual output after changes.
- **CI debugging starts from the URL.** When a workflow fails, fetch the run logs first (`gh run view --log-failed`). Do not guess at the cause.
- **Type-checking divergence.** Code that passes `mypy` locally may fail in CI where `--python-version 3.10` is used. Always consider the minimum supported Python version.
- **Simplify before adding.** When asked to improve something, first ask whether existing code or tools already cover the case. Remove dead code and unused abstractions before introducing new ones.
