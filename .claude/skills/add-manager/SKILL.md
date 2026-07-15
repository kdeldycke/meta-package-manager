---
name: add-manager
description: Add a new package manager to mpm
disable-model-invocation: true
---

# Add a new package manager

Implement support for a new package manager in `mpm`, or complete an incomplete integration. If adding a manager requested via a GitHub issue, extract CLI output samples from the issue body to guide the implementation.

## Choose an implementation strategy: class-based or config-based

Before writing anything, decide how the manager will be implemented. `mpm` supports two paths:

- **Class-based:** a Python module in `meta_package_manager/managers/`. Full power: multi-line or stateful output parsing, version pinning, per-operation search flags, conditional `sudo`, delegation, arbitrary logic. It is the most capable path, and what the rest of this document describes.
- **Config-based:** a declarative `[mpm.managers.<id>]` block that `mpm` turns into a live manager at startup, with no Python (documented in {doc}`/overrides`, "Define a new manager"). Quick to write, but constrained: each operation is a fixed argument list, and listings must parse either line-by-line with a single regex or as one flat top-level JSON array. The DSL covers sibling binaries (a per-operation `cli` key), unconditionally privileged operations (a per-operation `sudo = true` key plus a manager-level `default_sudo`), and version probes on a companion binary (`version_cli`, for suites versioned with the OS). A definition can live two places: in a user's own trusted configuration file (a private, per-machine manager), or bundled with `mpm` as read-only package data (a manager shipped to every user, like a built-in). The bundled path is how `mpm` distributes a simple manager as data instead of code.

Reach for config-based **only when every one of these holds**. If any fails, the manager needs a class:

| Requirement                                                                                                                | Rules out config-based when                                                                                                                                                                                                                                                                                                                                       |
| :------------------------------------------------------------------------------------------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A version command prints a regex-extractable version string, on the manager's own CLI or a `version_cli` companion binary. | No binary reports a usable version at all (like macOS `msupdate`).                                                                                                                                                                                                                                                                                                |
| `installed`, `outdated` and `search` each emit one package per line, or one flat top-level JSON array.                     | Records span multiple lines (`pacman -Ss`, `cabal list`, Solaris `pkginfo -x`) or the JSON is an object keyed by package or environment name (`mise`, `pixi`, `pnpm`).                                                                                                                                                                                            |
| One command per operation fully populates each package record.                                                             | A record needs enriching through a second, per-package call (`pacstall --cache-info` to fetch a version the listing omits): one operation is one command, so the DSL cannot chain the follow-up. A name-only listing is fine on its own (`apt-cyg list`, `swupd bundle-list`): `installed_version` is optional, so `mpm` yields those packages without a version. |
| Every mutating operation is one argument list with `{package_id}` or `{query}` substituted in.                             | An operation needs *conditional* `sudo` (static `sudo = true` is fine), delegation, or output post-processing. Query operations never escalate, so a listing that needs root (`deb-get`'s outdated piggybacks on `sudo deb-get update`) also rules the DSL out.                                                                                                   |
| The manager installs globally.                                                                                             | Packages are scoped to an activated project or environment (`flox`; `cabal outdated` is project-only).                                                                                                                                                                                                                                                            |
| Version pinning and native exact/extended search filtering are both unnecessary.                                           | The manager's whole point is selecting versions, or search must be resolved exactly server-side.                                                                                                                                                                                                                                                                  |

Config-based skips the class machinery: no Python module, no `pool.py` registration, no version pinning or delegation. A private definition needs nothing beyond your own config file; shipping one bundled adds only a short metadata checklist (see below). Reach for a class when the manager needs power the DSL cannot express, and upstream it if it would help others: {doc}`/overrides` and {doc}`/security` explain why a reviewed, shipped manager beats executable configuration.

Whatever the path, identify the tool's escalation model before mapping operations — each demands a different treatment:

- **Plain root-requiring** (most system managers): mark mutating operations privileged (`sudo = true` in a definition; `run_cli(..., sudo=True)` plus `default_sudo = True` in a class).
- **Self-escalating** (fink re-execs itself under `/usr/bin/sudo` and no-ops when already root): never mark operations privileged, or sudo stacks on sudo.
- **Broker-based** (pkcon hands transactions to a polkit-authorized daemon): no escalation at all; note that unattended runs depend on the broker's policy.
- **Root-refusing** (chromebrew hard-aborts as root): no escalation, and never wrap in sudo manually.

Also check whether the `platforms` tokens exist in extra-platforms (`VALID_PLATFORM_TOKENS` accepts any platform or group ID). A missing distro detection is an upstream extra-platforms addition (same author): land it there, track git main via `[tool.uv.sources]` until the release, then relax to the PyPI floor. The new-manager issue template's platform checklist derives from `MAIN_PLATFORMS` and is enforced by `test_new_package_manager_issue_template`, so regenerate it when platforms land.

## Config-based managers

The declarative schema (required keys, every operation, the regex and JSON parsers, placeholders, worked examples) is the "Define a new manager" section of {doc}`/overrides`, which is the source of truth. This section adds only the authoring workflow and the pitfalls that decide success.

1. **Capture real output first.** For each operation you plan to declare, run the actual CLI and paste its output. Confirm a single per-line regex or one flat JSON array can extract `package_id` (plus `installed_version` for `installed`, `latest_version` for `outdated`). Never assume a format. When the platform cannot run locally (OpenBSD, SliTaz, Solaris, ...), derive the format from upstream instead: read the exact `printf`/`echo`/`print` statements that emit each line in the tool's source, cite them, and mark reconstructed samples as source-derived in comments. Never invent output.

2. **Write the block.** Add `[mpm.managers.<id>]` with an `<id>` that no built-in uses. Set `platforms`, the `operations` table, and the identity fields (`cli_names`, `requirement`, `version_regexes`, ...). Silence color and interactivity via `pre_args`, `post_args` or `extra_env` (like `NO_COLOR = "1"`) so the parser sees clean text. `mpm config-template` prints the built-ins' overridable fields as a formatting reference.

3. **Declare only expressible operations.** A manager with no non-mutating "list upgradable" command (common: `soar`, `appman`, `gh extension`) omits `outdated`; `mpm` auto-skips it and `upgrade --all` still works. Never fake an operation with a mutating command.

4. **Validate against the real CLI.** `mpm` checks the definition at load and reports the first problem with a precise path:

   ```shell-session
   $ mpm --config ./my-managers.toml managers
   $ mpm --config ./my-managers.toml --<id> installed
   ```

5. **Add tests.** For a private definition, mirror `tests/test_manager_definition.py`: `parse_manager_definition` for validation cases, `build_manager_class(...)` with a monkeypatched `run_cli` for parsing, and the `fake_tool` fixture for an end-to-end run through a real subprocess. For a bundled definition, ship the `[samples]` fixtures in the TOML file itself instead (see the checklist below): the suite globs the shipped files and derives its checks from them.

Design around the DSL's fixed limits (all detailed in {doc}`/overrides`): no version pinning (`install` and `upgrade` always take the latest, `{version}` is never substituted); listings are line-by-line regex or a single flat JSON array, with no multi-line records, pagination, or value transforms; `search` cannot declare native exact or extended filtering, so `mpm` refilters the results itself. If any of these is load-bearing for the manager, stop and write a class instead.

### Where a config-based definition lives

A definition has two homes:

- **Private (a user's config).** Drop the `[mpm.managers.<id>]` block into your own configuration file. `mpm` picks it up on the next run: nothing else to touch, and it never leaves your machine.
- **Bundled (shipped with `mpm`).** Put the block in its own `meta_package_manager/managers/<id>.toml` file. `mpm` loads every shipped `*.toml` at startup and registers it like a built-in, so every user gets its `--<id>` flag. Bundled files are read-only package data, so they load without the config-file trust gate that guards a user's own definitions (see {doc}`/security`). `meta_package_manager/managers/gh_ext.toml` is the worked example.

Shipping a bundled definition is far lighter than the class-based checklist below, with no module:

| File                                      | Change                                                                                                                                                                                                                                                                                                                                                  |
| :---------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `meta_package_manager/managers/<id>.toml` | The definition (one `[mpm.managers.<id>]` section) plus a top-level `[samples]` table: a `[samples.version]` fixture locking the version probe, and one `[[samples.<operation>]]` block per declared query operation, locking each parser to a source-derived output sample. Auto-discovered: the loader and the sample-derived tests glob the file up. |
| `meta_package_manager/labels.py`          | Optional: ecosystem synonyms in `MANAGER_CONTENT_KEYWORDS`, and a `MANAGER_LABEL_GROUPS` entry if the manager joins an ecosystem group. The label and its baseline file/content rules derive from the pool.                                                                                                                                             |
| `docs/docs_update.py`                     | Optional: a well-known ecosystem alias in `KEYWORDS_EXTRAS` when it differs from the manager ID (like `gh-ext` and `github cli`). The ID lands in the PyPI keywords automatically.                                                                                                                                                                      |
| `tests/conftest.py`                       | Add a `PACKAGE_IDS` entry: the destructive install/remove round-trip covers bundled managers too, and the import-time assertion requires every shipped manager to carry one.                                                                                                                                                                            |
| `tests/test_pool.py`                      | Increment the `len(pool)` assertion in `test_manager_count`; `len(manager_classes)` stays.                                                                                                                                                                                                                                                              |
| `changelog.md`                            | A `- [<id>] Add ...` entry.                                                                                                                                                                                                                                                                                                                             |
| `docs/benchmark.yaml`                     | If the manager already had a competitor row, delete its `homepages:` entry: the homepage now comes from the definition (`test_benchmark_homepages_cover_non_pool_managers` enforces).                                                                                                                                                                   |

Then run `docs/docs_update.py` to regenerate the pool-derived blocks: the readme Sankey diagram and operations matrix, the PyPI keywords and the labeller rules in `pyproject.toml`. The benchmark and augmentations pages need no regeneration: their per-manager tables render live at Sphinx build time. A bundled config manager needs **no** `pool.py` import or `docs/meta_package_manager.managers.md` automodule: those are class-only.

## Completing an incomplete integration

External contributors often submit a working manager module (`managers/<name>.py`, `pool.py`, `conftest.py`) but skip the documentation and metadata files. See [kdeldycke/meta-package-manager#1758](https://github.com/kdeldycke/meta-package-manager/pull/1758) for a typical example: the PR added code and tests but was missing 10+ files.

When asked to "integrate further", "fill gaps", or "finish" a manager that already has code:

1. Read the existing manager module to understand supported operations and platforms.
2. Walk the **file checklist** below and check **every** file for the manager's presence. The most commonly missed files are: `docs/meta_package_manager.managers.md`, `labels.py` (group and synonyms), `test_pool.py` (manager count), and `changelog.md` — plus a `docs/docs_update.py` run to regenerate the pool-derived blocks (readme, keywords, labeller rules).
3. Verify the `requirement` version specifier by fetching the upstream release history. Check when the features the code depends on (like `--json` output) were actually introduced. Contributors often default to `>=1.0.0` without checking.
4. If the manager wraps or complements another (like sfsu wraps Scoop), merge them under a single `📦 manager:` label by grouping them in `labels.py`. Use the `-based` suffix convention for the group name (like `scoop-based`) to avoid colliding with the manager ID itself; the label and its rules regenerate from the group.
5. Fetch the upstream repository (README, releases, changelog) to verify CLI output formats match the parsing code.
6. Check class attribute ordering against the base class. The `test_content_order` test enforces that class-level attributes and methods follow the canonical order defined in `PackageManager`. Common mistakes: `version_regexes` before `post_args`, or `name` after `homepage_url`.
7. If the manager delegates operations to another manager's CLI, use the `Delegate` descriptor from `capabilities.py` instead of repeating `override_cli_path` boilerplate. See the **Delegating operations** section below.

## Choose a template

Pick an existing manager with a similar CLI as your starting point. Read the template file in full before starting.

| Pattern                      | Example                          | When to use                                                                                                                          |
| ---------------------------- | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| Simple regex parsing         | `snap.py`, `flatpak.py`          | CLI outputs fixed-width or whitespace-delimited text                                                                                 |
| JSON output                  | `npm.py`, `homebrew.py`          | CLI supports `--json` or structured output                                                                                           |
| Multiple compiled regexes    | `gem.py`, `dnf.py`               | Complex text output requiring several capture patterns                                                                               |
| Shell function wrapper       | `sdkman.py`                      | Manager is a shell function, not a standalone binary                                                                                 |
| Sibling binaries             | `nix.py`                         | Different operations use different CLI binaries in the same directory                                                                |
| Subclass of existing manager | `yay.py`, `paru.py`, `pacaur.py` | Manager is a drop-in replacement or wrapper for another manager already implemented                                                  |
| Delegate to another manager  | `sfsu.py`                        | Manager has its own CLI for read operations but delegates mutating operations (install, upgrade, remove) to another manager's binary |

Subclassing is the lightest option: `yay.py` is only 39 lines because it inherits almost everything from `pacman.py`. If the new manager shares the same CLI interface as an existing one, subclass it and override only what differs.

Delegation via `Delegate` is for managers that share the same package ecosystem but have different CLI interfaces. Unlike subclassing, the read operations (list, search, outdated) have completely different implementations, but mutating operations reuse the other manager's methods verbatim.

Typical manager modules range from 140 to 260 lines. Larger implementations (350-570 lines) tend to involve managers with unusual output formats or many edge cases like `fwupd.py`, `winget.py`, or `pkg.py`.

## Implementation

Create `meta_package_manager/managers/<name>.py`. Follow the import pattern, class structure, and `TYPE_CHECKING` block from your template exactly.

Class-level attributes and methods must follow the canonical order defined in `PackageManager` (enforced by `test_content_order`). The order is: `homepage_url`, `platforms`, `requirement`, `cli_names`, `cli_search_path`, `extra_env`, `pre_cmds`, `pre_args`, `post_args`, `version_cli_options`, `version_regexes`, then operations (`installed`, `outdated`, `search`, `install`, `upgrade_all_cli`, `upgrade_one_cli`, `remove`, `sync`, `cleanup`).

### Class attributes

Required:

- `homepage_url`: official project URL.
- `platforms`: use constants from `extra_platforms` (`ALL_PLATFORMS`, `LINUX_LIKE`, `MACOS`, `WINDOWS`, `UNIX_WITHOUT_MACOS`, etc.). Combine with tuples: `platforms = LINUX_LIKE, MACOS`.

Common optional:

- `requirement`: minimum version specifier (e.g., `">=2.0.0"`). Set this to the earliest version that supports all features the implementation depends on. If the code parses `--json` output, check the upstream release history to find when that flag was introduced. Do not default to `>=1.0.0` without verification.
- `cli_names`: tuple of binary names to search for. Defaults to `(lowercase_class_name,)`. Set explicitly when the binary name differs from the class name (e.g., `cli_names = ("nix-env",)` for class `Nix`).
- `version_regexes`: tuple of regex strings with a `(?P<version>...)` named group.
- `version_cli_options`: tuple of args to get version. Defaults to `("--version",)`.
- `pre_args`, `post_args`: global arguments prepended/appended to every CLI call. Use these for flags like `--no-color` or `--quiet` that apply to all operations.
- `extra_env`: dict of environment variables to suppress colors, pagers, interactive prompts, etc.
- `cli_search_path`: extra directories to find the binary (e.g., `("~/.sdkman/bin",)`).

### Operations

Each operation maps to one of these methods. Implement as many as the manager supports. Unimplemented operations are automatically skipped by `mpm`.

| Operation   | Method signature                            | Returns             | Notes                                                                                                                                       |
| ----------- | ------------------------------------------- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Installed   | `installed` (property)                      | `Iterator[Package]` | Yield packages with `id` and `installed_version`.                                                                                           |
| Outdated    | `outdated` (property)                       | `Iterator[Package]` | Yield packages with `id`, `installed_version`, and `latest_version`.                                                                        |
| Search      | `search(query, extended, exact)`            | `Iterator[Package]` | Decorate with `@search_capabilities(extended_support=..., exact_support=...)`. Yield with `id`, `latest_version`, optionally `description`. |
| Install     | `install(package_id, version=None)`         | `str`               | Decorate with `@version_not_implemented` if version pinning is unsupported.                                                                 |
| Upgrade all | `upgrade_all_cli()`                         | `tuple[str, ...]`   | Return `self.build_cli(...)`, not `self.run_cli(...)`.                                                                                      |
| Upgrade one | `upgrade_one_cli(package_id, version=None)` | `tuple[str, ...]`   | Same as above. Decorate with `@version_not_implemented` if needed.                                                                          |
| Remove      | `remove(package_id)`                        | `str`               | Optional.                                                                                                                                   |
| Sync        | `sync()`                                    | `None`              | Optional. For refreshing package metadata from remote sources.                                                                              |
| Cleanup     | `cleanup()`                                 | `None`              | Optional. For garbage collection, cache clearing, orphan removal.                                                                           |

Key helpers from the base class:

- `self.run_cli(*args, **kwargs)` executes the manager CLI and returns stdout.
- `self.build_cli(*args)` builds a command tuple without executing it (used by `upgrade_all_cli` and `upgrade_one_cli`).
- `self.package(id=..., ...)` creates a `Package` with `manager_id` pre-filled.
- `self.cli_path` resolves to the discovered binary path. Use `.parent` to find sibling binaries for operations that use a different CLI (see `nix.py` for `sync` and `cleanup`).

### Delegating operations to another manager

When a manager uses its own CLI for read operations but delegates mutating operations to another manager's binary, use the `Delegate` descriptor from `capabilities.py`:

```python
from ..capabilities import Delegate
from .scoop import Scoop


class SFSU(PackageManager):
    _scoop = Delegate(Scoop)

    # Read operations use sfsu's own CLI with JSON output.
    @property
    def installed(self) -> Iterator[Package]:
        output = self.run_cli("list", "--json")
        ...

    # Mutating operations delegate to scoop.
    install = _scoop.install
    upgrade_all_cli = _scoop.upgrade_all_cli
    upgrade_one_cli = _scoop.upgrade_one_cli
    remove = _scoop.remove
```

The `Delegate` factory resolves the target manager's CLI binary via `self.which()` and temporarily sets `_delegate_cli_path` on the instance so that `build_cli` routes the command through the target binary. The host manager's `post_args` are automatically suppressed during delegation.

Place `_scoop = Delegate(Scoop)` at the top of the class body (before `homepage_url`). Place individual delegation assignments (`install = _scoop.install`) in the canonical operation order, interspersed with the other operations.

Do **not** subclass when the two managers have completely different output formats for read operations. Subclassing is for managers that share the same CLI interface. Delegation is for managers that share the same package ecosystem but have different CLIs.

### CLI output guidelines

- Use `--long-form-options` for self-documenting CLIs.
- Suppress colors and emoji (`--no-color`, `--color=never`, etc.) via `post_args` or `extra_env`.
- Prefer machine-readable output (JSON, XML, CSV) over text parsing. When parsing text, use class-level compiled regexes with named groups.
- Include at least one CLI output sample in each method's docstring as a `.. code-block:: shell-session` block. This helps future maintainers verify parsing without access to the actual manager.
- Read {doc}`/falsehoods` to anticipate edge cases in package naming and versioning.

## Choosing the destructive-test package (`PACKAGE_IDS`)

The destructive suite runs `mpm --<id> install <pkg>` then `mpm --<id> remove <pkg>` against the real host, so `PACKAGE_IDS[<id>]` in `tests/conftest.py` must name a package that installs and uninstalls cleanly:

- **Tiny and fast**: no dependency tree, no services/daemons, no `/etc` config, a single self-contained binary.
- **Not relied upon**: avoid ubiquitous tools (`wget`, `curl`, `git`, `jq`, `openssl`). They are usually already installed (so the install step is a no-op) and removing them can break the host or the test runner.
- **Self-contained**, ideally a Rust or Go binary.
- **Verified to exist** in that manager's repo/registry, with the exact ID format the manager expects (a bare name, `category/name`, `bucket/name`, `Publisher.Package`, a numeric ID, ...). Check the real index before committing the choice: do not guess.

Reuse the established picks for consistency instead of inventing new ones:

| Ecosystem                                                           | Package                                         | Notes                                                                                 |
| ------------------------------------------------------------------- | ----------------------------------------------- | ------------------------------------------------------------------------------------- |
| Linux distros, Homebrew, FreeBSD (apt, dnf, pacman, apk, brew, ...) | `nyancat`                                       | Single-file C binary in nearly every distro, Homebrew and FreeBSD; zero reverse-deps. |
| Distros lacking `nyancat`                                           | `sl` (Solus, Void), `hello`, `lolcat` (OpenWrt) | Fall back only where `nyancat` is absent.                                             |
| Source-compiling managers (emerge, FreeBSD ports)                   | `games-misc/nyancat`, `net/nyancat`             | Compiles in seconds from one C file; use the `category/name` atom.                    |
| Functional managers (Guix, Nix)                                     | `hello`                                         | The canonical GNU demo package.                                                       |
| Windows binary stores (choco, scoop, sfsu, winget) and `stew`       | `hyperfine`                                     | One self-contained Rust binary; use the manager's ID format.                          |
| npm, Yarn                                                           | `ms`                                            | Zero-dependency, ~7 KB.                                                               |
| pip, uv                                                             | `pytz`                                          | Pure-Python, zero-dependency.                                                         |
| pipx, uvx                                                           | `pycowsay`                                      | Must expose a console-script entry point (a library like `pytz` fails here).          |
| gem, cpan, composer                                                 | `paint`, `Try::Tiny`, `ralouphie/getallheaders` | Smallest inert zero-dependency package native to the language.                        |

Special cases: managers that only ship large artifacts use their lightest option (`sdkman` → `jbang`); managers with no real per-package install reference themselves (`deb-get`, `topgrade`); `fwupd` must never use an ID that flashes firmware on real hardware. Add a short inline comment for any non-obvious ID (numeric App Store/Steam IDs, firmware GUIDs).

## File checklist

Every new manager touches the same set of files. This list is derived from all 30 manager-addition commits in the project history.

### Always required

| File                                      | Change                                                                                                                                                                                                                                                                                                                                     |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `meta_package_manager/managers/<name>.py` | The new manager implementation.                                                                                                                                                                                                                                                                                                            |
| `meta_package_manager/pool.py`            | Add import (sorted by module name) and class to `manager_classes` tuple (sorted case-insensitively by class name).                                                                                                                                                                                                                         |
| `tests/conftest.py`                       | Add `"<manager_id>": "<package_id>"` to `PACKAGE_IDS`. See [Choosing the destructive-test package](#choosing-the-destructive-test-package-package-ids) for the selection criteria and the canonical per-ecosystem picks. A missing entry aborts collection of the whole suite (`PACKAGE_IDS` is asserted against the pool at import time). |
| `tests/test_pool.py`                      | Increment both count assertions in `test_manager_count()`.                                                                                                                                                                                                                                                                                 |
| `changelog.md`                            | Add `- [<manager_id>] Add <Name> package manager with <operations> support.` under the current unreleased version.                                                                                                                                                                                                                         |
| `readme.md`                               | Regenerated by `docs/docs_update.py`: the Sankey diagram and the operations matrix derive from the pool.                                                                                                                                                                                                                                   |
| `docs/meta_package_manager.managers.md`   | Add `automodule` section for `meta_package_manager.managers.<name>` in alphabetical order.                                                                                                                                                                                                                                                 |
| `pyproject.toml`                          | Regenerated by `docs/docs_update.py`: the `keywords`, the label registry and the labeller file/content rules all derive from the pool. Nothing to hand-edit.                                                                                                                                                                               |
| `meta_package_manager/labels.py`          | If the manager belongs to an ecosystem group, add it to the appropriate frozenset in `MANAGER_LABEL_GROUPS`. If the manager creates a new group (standalone manager now gaining a wrapper), add a new group entry. Add ecosystem synonyms to `MANAGER_CONTENT_KEYWORDS` so issues mentioning them get labelled.                            |
| `docs/docs_update.py`                     | Add a well-known ecosystem alias to `KEYWORDS_EXTRAS` when it differs from the manager ID; the ID itself lands in the PyPI keywords automatically.                                                                                                                                                                                         |

### When applicable

| File                                                       | When                                                                                                                                      | Change                                                                                               |
| ---------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `.github/workflows/tests.yaml`                             | Manager can be installed on CI runners. Check if it's available via an existing package manager (like Scoop, apt, brew) on the target OS. | Add an install step in the manager setup section, near related managers.                             |
| `docs/benchmark.yaml`                                      | Manager already appears in the comparison table.                                                                                          | Delete its `homepages:` entry: the homepage now comes from the class (a sync test enforces the set). |
| `.github/workflows/tests-install.yaml` + `docs/install.md` | Manager is a *distributor of mpm itself* (like Homebrew, Scoop, Nix, or an AUR helper). Most managers are not.                            | Add a CI job testing `mpm` installation via the new channel, and a matching tab in the install docs. |

## Validate

```shell-session
$ uv run -- pytest tests/test_pool.py tests/test_managers.py -x -q
$ uv run --group typing mypy meta_package_manager/managers/<name>.py
```

The test suite enforces: valid ID format, homepage URL, platform declarations, version regexes, no duplicate IDs, correct pool count, canonical attribute ordering (`test_content_order`), and label group disjointness.

Common validation failures after adding a manager:

- **`test_manager_count`**: forgot to increment the count in `test_pool.py`.
- **`test_content_order`**: class attributes are not in the canonical order (like `version_regexes` before `post_args`).
- **Label group collision**: the group name in `labels.py` collides with a manager ID. Use the `-based` suffix (like `scoop-based`, `pip-based`).
- **Whole-suite collection abort**: `tests/conftest.py` asserts `PACKAGE_IDS` covers exactly the class managers at import time; a missing class entry (or a stray bundled one) kills every test, not one.
- **`test_docstring_corpus`**: the `$ ...` shell-session samples in operation docstrings are checked against the real CLI construction. Write them in build order: binary, `pre_args`, the declared arguments with the package ID exactly where the code puts it, `post_args` last (`pkcon install --noninteractive hello --plain`, not `pkcon install hello --noninteractive --plain`).
- **`test_new_package_manager_issue_template`**: the issue template's platform checklist is generated from `MAIN_PLATFORMS`; it goes stale when an extra-platforms release adds detections.
