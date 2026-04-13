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
verbosity = "INFO"
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

These go under `[mpm]` (or `[tool.mpm]` in `pyproject.toml`):

| Key | Type | Default | Description |
| :-- | :--- | :------ | :---------- |
| `verbosity` | string | `"INFO"` | Logging level: `CRITICAL`, `ERROR`, `WARNING`, `INFO`, or `DEBUG`. |
| `timeout` | integer | `500` | Maximum duration in seconds for each manager CLI call. |
| `ignore_auto_updates` | boolean | `true` | Exclude auto-updating packages from outdated/upgrade results. |
| `stop_on_error` | boolean | `false` | Stop on first manager CLI error instead of continuing. |
| `dry_run` | boolean | `false` | Simulate CLI calls without performing any action. |
| `all_managers` | boolean | `false` | Force evaluation of all managers, including unsupported and deprecated. |
| `description` | boolean | `false` | Show package description in results. |
| `sort_by` | string | `"manager_id"` | Sort results by: `manager_id`, `manager_name`, `package_id`, `package_name`, or `version`. |
| `stats` | boolean | `true` | Print per-manager package statistics. |
| `table_format` | string | `"rounded-outline"` | Table rendering style (see `mpm --help` for all choices). |

### Subcommand options

These go under `[mpm.<subcommand>]` (or `[tool.mpm.<subcommand>]`):

**`[mpm.search]`**

| Key | Type | Default | Description |
| :-- | :--- | :------ | :---------- |
| `exact` | boolean | `false` | Only return exact matches instead of fuzzy search. |
| `extended` | boolean | `false` | Extend search to description and other package attributes. |
| `refilter` | boolean | `true` | Re-filter results locally when the manager's search is too loose. |

**`[mpm.installed]`**

| Key | Type | Default | Description |
| :-- | :--- | :------ | :---------- |
| `duplicates` | boolean | `false` | Only list packages installed by more than one manager. |

**`[mpm.outdated]`**

| Key | Type | Default | Description |
| :-- | :--- | :------ | :---------- |
| `plugin_output` | boolean | `false` | Render output for Xbar/SwiftBar plugin consumption. |

**`[mpm.upgrade]`**

| Key | Type | Default | Description |
| :-- | :--- | :------ | :---------- |
| `all` | boolean | `false` | Upgrade all outdated packages (not just those specified). |

**`[mpm.backup]`**

| Key | Type | Default | Description |
| :-- | :--- | :------ | :---------- |
| `overwrite` | boolean | `false` | Allow overwriting an existing backup file. |
| `merge` | boolean | `false` | Merge new packages into an existing backup file. |
| `update_version` | boolean | `false` | Update version of packages already in the backup file. |

**`[mpm.sbom]`**

| Key | Type | Default | Description |
| :-- | :--- | :------ | :---------- |
| `spdx` | boolean | `true` | Use SPDX format (`false` for CycloneDX). |
| `overwrite` | boolean | `false` | Allow overwriting an existing SBOM file. |

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

# Sort by package name instead of manager.
sort_by = "package_name"

# Output as JSON for scripting.
table_format = "json"

[mpm.search]
# Use exact matching.
exact = true

[mpm.backup]
# Merge into existing backup files by default.
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
info: User selection of managers by priority: > flatpak > pipx
info: Managers dropped by user: None
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

## Troubleshooting

You can easily debug the way `mpm` sources its configuration with `--show-params`:

```{click:run}
from meta_package_manager.cli import mpm
invoke(mpm, args=["--table-format", "vertical", "--show-params"])
```
