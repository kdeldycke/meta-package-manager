# {octicon}`sliders` Configuration

All `mpm` options can be set with a configuration file.

## Location

Configuration is auto-discovered from two places, in order of priority:

1. **`pyproject.toml`**: searched from the current working directory upward to the nearest VCS root (`.git`, `.hg`, etc.), using a `[tool.mpm]` section. This follows the same discovery pattern as `uv`, `ruff`, and `mypy`.
2. **Dedicated config file**: searched in the platform-specific application directory.

| Platform | Folder                                 |
| :------- | :------------------------------------- |
| macOS    | `~/Library/Application Support/mpm/`   |
| Unix     | `~/.config/mpm/`                       |
| Windows  | `C:\Users\<user>\AppData\Roaming\mpm\` |

The dedicated config file can be TOML, YAML, JSON, or any format supported by click-extra (install [extra dependencies](install.md#extra-dependencies) for additional format support). An explicit `--config` flag always takes precedence over auto-discovery.

## File format

### Standalone TOML

A typical `~/.config/mpm/config.toml`:

```toml
[mpm]
verbosity = "WARNING"
timeout = 300
flatpak = true
pipx = true

[mpm.search]
exact = true
```

### `pyproject.toml`

The same configuration embedded in a project's `pyproject.toml`:

```toml
[tool.mpm]
timeout = 300
pip = false

[tool.mpm.search]
exact = true
```

The `[tool.mpm]` section maps directly to `[mpm]` in a standalone config file. The `[tool]` prefix is stripped automatically.

## Available options

Every CLI option on the root `mpm` group and its subcommands can be set in the configuration file. The TOML key is the option name with leading dashes removed and remaining dashes replaced by underscores (or kept as-is for manager IDs like `apt-mint`).

### Global options

These go under `[mpm]` (or `[tool.mpm]` in `pyproject.toml`). The reference below is rendered live from {py:class}`meta_package_manager.config.MpmConfig`, the typed schema that also backs `--validate-config`, so it cannot drift from the code:

```{click:config} mpm
from meta_package_manager.cli import mpm
```

See the [release-age cooldown](#release-age-cooldown) section below for the safeguard behind `cooldown` and `require_cooldown_support`, and [privilege escalation](sudo.md) for the model behind `sudo`.

Click-extra's built-in options ride the same configuration pipeline. The most useful ones:

| Key            | Type    | Default             | Description                                                                                                                                                                                                        |
| :------------- | :------ | :------------------ | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `verbosity`    | string  | `"WARNING"`         | Logging level: `CRITICAL`, `ERROR`, `WARNING`, `INFO`, or `DEBUG`.                                                                                                                                                 |
| `progress`     | boolean | `true`              | Show a progress spinner on stderr during long manager CLI calls. Self-disabled off a terminal (pipes, `TERM=dumb`, CI) and by `--accessible`; mpm also suppresses it for serialized output and at DEBUG verbosity. |
| `table_format` | string  | `"rounded-outline"` | Table rendering style (see `mpm --help` for all choices).                                                                                                                                                          |

### Release-age cooldown

`cooldown` is a supply-chain safeguard: it refuses to install or upgrade any package version published more recently than the given age, giving a freshly-published (and possibly compromised) release time to be caught and pulled before it reaches the system.

`mpm` enforces the cooldown through each manager's own release-age mechanism, so coverage is limited to the managers `mpm` can gate: `uv` and `uvx` (via `exclude-newer`), `npm` (via `min-release-age`), `pnpm` (via `minimumReleaseAge`), `pip` (via `--uploaded-prior-to`), `pipx` (which inherits the pip setting), and `yay` (through a generated Lua-hook overlay, since yay ships no release-age option of its own). Managers without native support cannot honor the gate. By default they are skipped during install and upgrade (fail-closed), so nothing slips in unguarded. Pass `--allow-unsupported-managers` (or set `require_cooldown_support = false`) to run them anyway, without the safeguard. Read-only operations (`outdated`, `installed`, `search`) are never blocked.

See {doc}`cooldown` for the full support matrix and the rationale.

The value is a duration like `7 days`, `1 week`, `12h` or `30m`; a bare number is read as a count of days, and `0` (or an empty string) disables the gate.

```toml
[mpm]
# Only let releases that are at least a week old into the system.
cooldown = "1 week"
```

### Accessibility

The `--accessible` flag (or the `ACCESSIBLE=1` environment variable) is a shortcut for `--no-color --table-format plain`: it strips ANSI codes and replaces Unicode box-drawing characters with plain ASCII, so the output is friendly to screen readers and braille displays.

```{code-block} shell-session
$ mpm --accessible managers
```

An explicit `--color` / `--no-color` or `--table-format` setting (on the command line, in an environment variable, or in this configuration file) keeps precedence over `--accessible`, so you can toggle a single dimension back on:

```{code-block} shell-session
$ mpm --accessible --table-format rounded-outline managers
```

### Subcommand options

These go under `[mpm.<subcommand>]` (or `[tool.mpm.<subcommand>]`):

**`[mpm.search]`**

| Key        | Type    | Default | Description                                                       |
| :--------- | :------ | :------ | :---------------------------------------------------------------- |
| `exact`    | boolean | `false` | Only return exact matches instead of fuzzy search.                |
| `extended` | boolean | `false` | Extend search to description and other package attributes.        |
| `refilter` | boolean | `true`  | Re-filter results locally when the manager's search is too loose. |

**`[mpm.installed]`**

| Key          | Type    | Default | Description                                                                          |
| :----------- | :------ | :------ | :----------------------------------------------------------------------------------- |
| `duplicates` | boolean | `false` | Only list packages installed by more than one manager.                               |
| `exact`      | boolean | `false` | With a `QUERY`, require a verbatim match on the package ID or name instead of fuzzy. |

**`[mpm.outdated]`**

| Key             | Type    | Default | Description                                                                          |
| :-------------- | :------ | :------ | :----------------------------------------------------------------------------------- |
| `exact`         | boolean | `false` | With a `QUERY`, require a verbatim match on the package ID or name instead of fuzzy. |
| `plugin_output` | boolean | `false` | Render output for Xbar/SwiftBar plugin consumption.                                  |

**`[mpm.upgrade]`**

| Key   | Type    | Default | Description                                               |
| :---- | :------ | :------ | :-------------------------------------------------------- |
| `all` | boolean | `false` | Upgrade all outdated packages (not just those specified). |

**`[mpm.dump]`** (also reachable as `[mpm.backup]`, `[mpm.lock]`, `[mpm.freeze]`, `[mpm.snapshot]`)

| Key              | Type    | Default | Description                                                                               |
| :--------------- | :------ | :------ | :---------------------------------------------------------------------------------------- |
| `toml`           | boolean | `true`  | Emit a TOML manifest with one section per manager.                                        |
| `brewfile`       | boolean | `false` | Emit a Brewfile instead of a TOML manifest (managers supported by `brew bundle` only).    |
| `header`         | boolean | `true`  | Include a metadata + warning comment block at the top of the output.                      |
| `overwrite`      | boolean | `false` | Allow overwriting an existing output file.                                                |
| `merge`          | boolean | `false` | TOML only. Add each new entry to an existing file.                                        |
| `update_version` | boolean | `false` | TOML only. Update each existing entry with the version currently installed on the system. |
| `query`          | string  | `""`    | Only snapshot installed packages whose ID or name matches this query.                     |
| `exact`          | boolean | `false` | With a `query`, require a verbatim match on the package ID or name instead of fuzzy.      |

**`[mpm.sbom]`**

| Key         | Type    | Default | Description                                                                                                                                                                        |
| :---------- | :------ | :------ | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `spdx`      | boolean | `true`  | Use SPDX format (`false` for CycloneDX).                                                                                                                                           |
| `bundled`   | boolean | `true`  | Bundled mode: query each manager for richer metadata and merge per-package upstream SBOMs into the aggregate. Set `false` for fast inventory snapshots (name, version, purl only). |
| `overwrite` | boolean | `false` | Allow overwriting an existing SBOM file.                                                                                                                                           |
| `query`     | string  | `""`    | Only export installed packages whose ID or name matches this query.                                                                                                                |
| `exact`     | boolean | `false` | With a `query`, require a verbatim match on the package ID or name instead of fuzzy.                                                                                               |

## Full example

```toml
# ~/.config/mpm/config.toml

[mpm]
# Only consider Homebrew and Pip by default.
brew = true
pip = true

# Increase timeout for slow connections.
timeout = 600

# Always show package descriptions.
description = true

# Sort by package name, then manager ID as a tie-breaker (repeat for priority order).
sort_by = ["package_name", "manager_id"]

# Output as JSON for scripting.
table_format = "json"

[mpm.search]
# Use exact matching.
exact = true

[mpm.dump]
# Merge into existing snapshot files by default.
merge = true
```

## Selecting managers

### Default managers

You can select which package managers `mpm` considers by default. Setting a manager to `true` restricts `mpm` to that manager:

```toml
[mpm]
flatpak = true
pipx = true
```

This is equivalent to always passing `--flatpak --pipx` on the command line.

```shell-session
$ mpm managers
╭────────────┬─────────┬────────────────────┬──────────────────────────┬────────────┬─────────╮
│ Manager ID │ Name    │ Supported          │ CLI                      │ Executable │ Version │
├────────────┼─────────┼────────────────────┼──────────────────────────┼────────────┼─────────┤
│ flatpak    │ Flatpak │ ✘ BSD, Linux, Unix │ ✘ flatpak not found      │            │         │
│ pipx       │ Pipx    │ ✓                  │ ✓ /opt/homebrew/bin/pipx │ ✓          │ ✓ 1.7.1 │
╰────────────┴─────────┴────────────────────┴──────────────────────────┴────────────┴─────────╯
```

````{hint}
There is an alternative syntax to specify default managers, which is to use the `manager` key:
```toml
[mpm]
manager = ["flatpak", "pipx"]
```

It calls `mpm` with the `--manager flatpak` and `--manager pipx` parameters instead of `--flatpak` and `--pipx`.

It is equivalent to the previous example, but call the hidden `--manager` parameter. This parameter is not shown in the help message as it is less user-friendly.

You can still mix both syntax in the same configuration file, as well as on the command line.
````

### Ignore a manager

Setting a manager to `false` excludes it. [This user](https://github.com/matryer/xbar/issues/777) wanted `mpm` to always ignore `pip` to speed up execution:

```toml
[mpm]
pip = false
```

````{hint}
There is an alternative syntax to ignore managers:
```toml
[mpm]
exclude = ["pip", "pipx"]
```

It calls `mpm` with the `--exclude pip` and `--exclude pipx` parameters, which is the equivalent of `--no-pip` and `--no-pipx` options.

The `--exclude` parameter is advertised in the help message as it is less user-friendly than single `--no-<manager>` flags.

You can still mix both syntax in the same configuration file, as well as on the command line.
````

### Overlapping managers

`mpm` supports some overlapping package managers. Take for instance `pacman` and its collection of AUR helpers like `paru` and `yay`. All of these alternatives have the same source of packages as `pacman`. So updates to a single package may show up multiple times, because AUR helpers depends on `pacman` (which is always installed on the system).

You can fine-tune this behaviour by simply excluding redundant managers depending on your preferences.

For instance, if `yay` is your preferred helper and `pacman` and `paru` are polluting your entries, you can setup a configuration file in `~/.config/mpm/config.toml` to exclude the other AUR helpers by default:

```toml
[mpm]
pacman = false
paru = false
```

## Per-manager overrides

Each built-in manager exposes a small set of attributes (CLI names, search paths, timeouts, ...) that can be tuned from the configuration file using a `[mpm.managers.<id>]` section. A section keyed by an ID that is not a built-in instead **defines a brand-new manager** from configuration. See {doc}`overrides` for both the override schema and the definition schema, plus the `mpm config-template` helper that prints a ready-to-paste block. Because a definition makes `mpm` run the commands you declare, read {doc}`security` first.

## Precedence

Options are resolved in this order, from highest to lowest priority:

1. Command-line flags (`--timeout 300`).
2. Environment variables (`MPM_TIMEOUT=300`).
3. Configuration file values.
4. Built-in defaults.

## Validation

Use `--validate-config` to check a configuration file for errors without running a command:

```shell-session
$ mpm --validate-config ~/.config/mpm/config.toml
Configuration file /home/user/.config/mpm/config.toml is valid.
```

This validates option names against the CLI parameters and reports unknown keys.

## Exporting the resolved configuration

`--export-config FORMAT` prints the fully-resolved configuration: every option's effective value once the config file, environment variables, and built-in defaults have been merged. It then exits without running any command. Where `--params` below is a debug table of *where* each value came from, this emits a clean document you can save straight back as a config file.

`FORMAT` is one of `toml`, `yaml`, `json`, `json5`, `jsonc`, `hjson`, or `xml`:

```{click:run}
from meta_package_manager.cli import mpm
invoke(mpm, args=["--export-config", "toml"])
```

For instance, `mpm --export-config toml > ~/.config/mpm/config.toml` seeds a config file from your live setup.

## Troubleshooting

You can easily debug the way `mpm` sources its configuration with `--params`:

```{click:run}
from meta_package_manager.cli import mpm
invoke(mpm, args=["--table-format", "vertical", "--params"])
```

## `meta_package_manager.config` API

```{eval-rst}
.. automodule:: meta_package_manager.config
   :members:
   :show-inheritance:
   :undoc-members:
```
