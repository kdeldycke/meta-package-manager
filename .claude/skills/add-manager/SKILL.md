---
name: add-manager
description: Add a new package manager to mpm
disable-model-invocation: true
---

# Add a new package manager

Implement support for a new package manager in `mpm`. If adding a manager requested via a GitHub issue, extract CLI output samples from the issue body to guide the implementation.

## Choose a template

Pick an existing manager with a similar CLI as your starting point. Read the template file in full before starting.

| Pattern                      | Example                          | When to use                                                                         |
| ---------------------------- | -------------------------------- | ----------------------------------------------------------------------------------- |
| Simple regex parsing         | `snap.py`, `flatpak.py`          | CLI outputs fixed-width or whitespace-delimited text                                |
| JSON output                  | `npm.py`, `homebrew.py`          | CLI supports `--json` or structured output                                          |
| Multiple compiled regexes    | `gem.py`, `dnf.py`               | Complex text output requiring several capture patterns                              |
| Shell function wrapper       | `sdkman.py`                      | Manager is a shell function, not a standalone binary                                |
| Sibling binaries             | `nix.py`                         | Different operations use different CLI binaries in the same directory               |
| Subclass of existing manager | `yay.py`, `paru.py`, `pacaur.py` | Manager is a drop-in replacement or wrapper for another manager already implemented |

Subclassing is the lightest option: `yay.py` is only 39 lines because it inherits almost everything from `pacman.py`. If the new manager shares the same CLI interface as an existing one, subclass it and override only what differs.

Typical manager modules range from 140 to 260 lines. Larger implementations (350-570 lines) tend to involve managers with unusual output formats or many edge cases like `fwupd.py`, `winget.py`, or `pkg.py`.

## Implementation

Create `meta_package_manager/managers/<name>.py`. Follow the import pattern, class structure, and `TYPE_CHECKING` block from your template exactly.

### Class attributes

Required:

- `homepage_url`: official project URL.
- `platforms`: use constants from `extra_platforms` (`ALL_PLATFORMS`, `LINUX_LIKE`, `MACOS`, `WINDOWS`, `UNIX_WITHOUT_MACOS`, etc.). Combine with tuples: `platforms = LINUX_LIKE, MACOS`.

Common optional:

- `requirement`: minimum version specifier (e.g., `">=2.0.0"`).
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

### CLI output guidelines

- Use `--long-form-options` for self-documenting CLIs.
- Suppress colors and emoji (`--no-color`, `--color=never`, etc.) via `post_args` or `extra_env`.
- Prefer machine-readable output (JSON, XML, CSV) over text parsing. When parsing text, use class-level compiled regexes with named groups.
- Include at least one CLI output sample in each method's docstring as a `.. code-block:: shell-session` block. This helps future maintainers verify parsing without access to the actual manager.
- Read {doc}`/falsehoods` to anticipate edge cases in package naming and versioning.

## File checklist

Every new manager touches the same set of files. This list is derived from all 30 manager-addition commits in the project history.

### Always required

| File                                      | Change                                                                                                             |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `meta_package_manager/managers/<name>.py` | The new manager implementation.                                                                                    |
| `meta_package_manager/pool.py`            | Add import (sorted by module name) and class to `manager_classes` tuple (sorted case-insensitively by class name). |
| `tests/conftest.py`                       | Add `"<manager_id>": "<package_name>"` to `PACKAGE_IDS`. Choose a small, low-impact package for destructive tests. |
| `tests/test_pool.py`                      | Increment both count assertions in `test_manager_count()`.                                                         |
| `changelog.md`                            | Add `- [<manager_id>] Add <Name> package manager with <operations> support.` under the current unreleased version. |

### Almost always required

| File                                  | Change                                                                                                                                                                   |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `pyproject.toml`                      | Add manager name (and ecosystem name if different) to `keywords`. Add `"📦 manager: <name>"` entries to both `labels.extra-file-rules` and `labels.extra-content-rules`. |
| `readme.md` + `extra-labels/mpm.toml` | Regenerated automatically. Run `uv run -- python docs/docs_update.py`.                                                                                                   |

### When applicable

| File                                                       | When                                                                                                                                      | Change                                                                                               |
| ---------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `meta_package_manager/labels.py`                           | Manager belongs to an existing ecosystem (e.g., adding an AUR helper to the pacman-based group, or a pip wrapper to the pip-based group). | Add the manager ID to the appropriate frozenset in `MANAGER_LABEL_GROUPS`.                           |
| `docs/benchmark.md`                                        | Manager already appears in the comparison table.                                                                                          | Add `✓` in the `mpm` column.                                                                         |
| `.github/workflows/tests-install.yaml` + `docs/install.md` | Manager is a *distributor of mpm itself* (like Homebrew, Scoop, Nix, or an AUR helper). Most managers are not.                            | Add a CI job testing `mpm` installation via the new channel, and a matching tab in the install docs. |

## Validate

```shell-session
$ uv run -- pytest tests/test_pool.py tests/test_managers.py -x -q
$ uv run --group typing mypy meta_package_manager/managers/<name>.py
```

The test suite enforces: valid ID format, homepage URL, platform declarations, version regexes, no duplicate IDs, correct pool count, and alphabetical ordering.
