# {octicon}`pin` Per-manager overrides

Each built-in manager exposes a small set of attributes that can be overridden from the configuration file. Add a `[mpm.managers.<id>]` section (or `[tool.mpm.managers.<id>]` in `pyproject.toml`) for each manager you want to tune. Values from the file take precedence over the built-in defaults and over the matching global `[mpm]` settings or `--<flag>` command-line values when both apply to the same field.

(overridable-fields)=

## Overridable fields

| Field                 | Type             | Description                                                                                                                                                                          |
| :-------------------- | :--------------- | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `cli_names`           | list of strings  | CLI binary names to look for, in order of priority.                                                                                                                                  |
| `cli_search_path`     | list of strings  | Extra directories searched **before** `$PATH` for the binary.                                                                                                                        |
| `deprecated`          | boolean          | Mark a manager as deprecated, hiding it from default selection.                                                                                                                      |
| `dry_run`             | boolean          | Simulate CLI calls without performing any action, only for this manager.                                                                                                             |
| `extra_env`           | table of strings | Additional environment variables passed to every CLI call.                                                                                                                           |
| `ignore_auto_updates` | boolean          | Exclude auto-updating packages from outdated/upgrade results, only for this manager.                                                                                                 |
| `post_args`           | list of strings  | Arguments appended **after** every CLI invocation.                                                                                                                                   |
| `pre_args`            | list of strings  | Arguments inserted **before** every CLI invocation.                                                                                                                                  |
| `pre_cmds`            | list of strings  | Commands prepended to every CLI invocation (typically `sudo`).                                                                                                                       |
| `requirement`         | string           | PEP 440-style version requirement the manager must satisfy to be considered available.                                                                                               |
| `stop_on_error`       | boolean          | Stop on the first CLI error from this manager instead of continuing.                                                                                                                 |
| `sudo`                | boolean          | Run this manager's privileged operations through `sudo` (overrides its built-in default: system managers escalate, user-level managers do not). See [privilege escalation](sudo.md). |
| `timeout`             | integer          | Maximum duration in seconds for each CLI call from this manager.                                                                                                                     |
| `version_cli_options` | list of strings  | CLI options used to extract the manager's reported version.                                                                                                                          |
| `version_regexes`     | list of strings  | Regular expressions tried in order to extract the version from CLI output.                                                                                                           |

```{important}
List-valued fields use **replace** semantics: an override fully supersedes the built-in default rather than merging with it. For example, setting `cli_search_path = ["/opt/bin"]` on a manager that ships with `cli_search_path = ("/usr/local/bin",)` results in `("/opt/bin",)`, not the union of both.
```

## Discover the override template

Run `mpm config-template` to print the current overridable attributes of every maintained manager as a ready-to-paste config block. Pass one or more manager IDs to narrow the output:

```shell-session
$ mpm config-template winget > my-overrides.toml
$ mpm config-template brew pip cargo
```

The output lists every overridable field with its current value, so it doubles as the canonical reference for what each manager exposes. Prune the rows that don't apply and customize the rest. The output is valid TOML; redirect it directly into a config file or merge it into your existing `[mpm]` section.

## Example: bypass a Windows app-store placeholder

Modern Windows ships placeholder executables under `%LOCALAPPDATA%\Microsoft\WindowsApps\` that, when invoked, open the Microsoft Store rather than running the real CLI. If you have installed the genuine `winget` somewhere else, point `cli_search_path` at that directory so `mpm` finds it first:

```toml
[mpm.managers.winget]
cli_search_path = [
  "C:\\Program Files\\WindowsApps\\Microsoft.DesktopAppInstaller_1.27.0_x64",
]
```

The override directories are searched before `$PATH`, so the real binary wins over the store placeholder.

## Example: relax a version requirement

A few managers gate themselves behind a minimum version. If you ship a custom build that reports an unconventional version string, override `requirement`:

```toml
[mpm.managers.guix]
requirement = ">=0.0"
```

## Example: per-manager timeout and quiet mode

Slow managers can be given a longer timeout without affecting the rest of the pool. Combine with `pre_args` to silence chatty output:

```toml
[mpm.managers.brew]
timeout = 900

[mpm.managers.cargo]
pre_args = ["--quiet", "--color", "never"]
```

## Validation

Unknown manager IDs and unknown field names are reported as warnings on `<stderr>` and skipped: a typo will not crash `mpm`. Type mismatches (a single string passed where a list is expected) raise an error so the offending value can be corrected.

(define-a-new-manager)=

## Define a new manager

A `[mpm.managers.<id>]` section whose ID is **not** a built-in manager defines a brand-new manager rather than overriding one. `mpm` builds it at startup and treats it like any built-in: it gets its own `--<id>` / `--no-<id>` selectors, joins the default set on its supported platforms, and is driven by every subcommand it implements.

```{important}
A manager definition makes `mpm` run the commands you declare. Definitions are only loaded from a trusted, local configuration file (owned by you, not world-writable, never a remote `--config` URL). Read {doc}`security` before adding one.
```

### Required keys

| Key          | Type            | Description                                                                                                 |
| :----------- | :-------------- | :---------------------------------------------------------------------------------------------------------- |
| `platforms`  | list of strings | Platform or group IDs the manager runs on (like `linux`, `macos`, `all_platforms`, or a specific `ubuntu`). |
| `operations` | table           | At least one operation (see below). A manager with no operations does nothing.                              |

Every [overridable field](#overridable-fields) (`cli_names`, `cli_search_path`, `requirement`, `version_regexes`, `pre_args`, `extra_env`, `timeout`, ...) may also be set, plus `name` and `homepage_url`. When `cli_names` is omitted it defaults to the manager ID.

Five definition-only fields have no override counterpart:

| Key                     | Type    | Description                                                                                                                                                                                                                                           |
| :---------------------- | :------ | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `brewfile_entry_type`   | string  | Name of the [Homebrew Bundle DSL](https://docs.brew.sh/Brew-Bundle-and-Brewfile) entry this manager maps to (`vscode`, `cargo`, ...), so its installed packages join `mpm dump --brewfile` exports. Omit it for managers with no Brewfile equivalent. |
| `brewfile_skip_warning` | string  | Warning emitted when this manager's installed packages are deliberately left out of a Brewfile export, where staying silent would mislead. Supports a `{count}` placeholder for the number of packages skipped.                                       |
| `default_sudo`          | boolean | The manager's built-in escalation policy: operations marked `sudo = true` escalate by default. The user's global `--sudo`/`--no-sudo` flag or a `sudo` override still win. See [privilege escalation](sudo.md).                                       |
| `internal_sudo`         | boolean | Marks a manager whose CLI invokes `sudo` itself mid-run, like `fink`: `mpm` never wraps its commands, and instead reuses a warm credential cache or warns when a silent call may be hiding a password prompt. See [privilege escalation](sudo.md).    |
| `version_cli`           | string  | Alternate binary probed for the manager's version, for tool suites whose own binaries report none (OpenBSD's `pkg_add`: the suite is versioned with the OS, so `uname` reports it). Probed with `version_cli_options`, parsed with `version_regexes`. |

### Operations

Each entry under `[mpm.managers.<id>.operations]` declares one operation. Every operation takes an `args` list appended after the resolved binary. An operation may also name its own `cli` (a sibling binary resolved on the same search path), so one definition can span a multi-binary suite: `urpmq` searching while `urpmi` installs and `urpme` removes. Without `cli`, the operation runs the manager's main binary.

**Command operations** run a CLI and need nothing else. Any operation may add `sudo = true` to mark itself privileged, mirroring the escalation flag built-in managers set in code: whether it actually escalates follows the usual policy (the definition's `default_sudo`, then the global `--sudo`/`--no-sudo` flag). Command operations are the usual bearers; a query may also carry it, for the rare tool that gates even its read-only listings behind root (`deb-get`'s upgradable check).

| Operation        | Required placeholder | Maps to                                              |
| :--------------- | :------------------- | :--------------------------------------------------- |
| `install`        | `{package_id}`       | `mpm install`                                        |
| `remove`         | `{package_id}`       | `mpm remove`                                         |
| `remove_orphan`  | `{package_id}`       | `mpm remove --orphans`                               |
| `upgrade_one`    | `{package_id}`       | single-package `mpm upgrade` (needs `installed` too) |
| `upgrade_all`    | none                 | `mpm upgrade --all`                                  |
| `sync`           | none                 | `mpm sync`                                           |
| `cleanup_orphan` | none                 | `mpm cleanup --orphans`                              |
| `cleanup_cache`  | none                 | `mpm cleanup --cache`                                |
| `cleanup_repair` | none                 | `mpm cleanup --repair`                               |
| `doctor`         | none                 | `mpm doctor` (read-only diagnosis)                   |

There is no `cleanup` operation to declare: a plain `mpm cleanup` runs the declared `cleanup_cache` and `cleanup_repair` categories, and `mpm cleanup --orphans` the declared `cleanup_orphan`, so a definition carrying the old monolithic `cleanup` key is rejected with an error naming the three category keys. Declare `cleanup_cache` for a cache-pruning command, `cleanup_orphan` for an orphan sweep.

**Query operations** (`installed`, `outdated`, `orphans`, `search`) parse the command's output. `orphans` backs `mpm orphans`, the read-only listing of packages installed as dependencies that nothing requires anymore. `search` may embed the `{query}` placeholder in its `args`; omitting it is also valid for tools with no real search command, whose `search` then lists the whole catalog (`opkg list`, `swupd bundle-list --all`) and relies on `mpm`'s client-side refiltering to narrow the results. Provide *either* a `regex` matched against each output line, *or* a JSON parser (`format = "json"` with a `fields` mapping and optional `list_path`). Both map these recognized fields to a package:

- `package_id` (always required),
- `installed_version` (optional: some tools track no per-package version, like `swupd`'s Clear Linux bundles),
- `latest_version` (required by `outdated`).

A JSON field maps to a key name, optionally suffixed with a `[N]` list index to pick one element out of a list-valued key: `installed_version = "installed_versions[0]"` reads the first entry of each package's version array.

When the tool has native switches for `mpm search`'s refinements, `search` can declare them as argument templates: `exact_args` (spliced in when `--exact` is requested), `extended_args` (when `--extended` reaches into descriptions) and `id_name_only_args` (for tools whose *unrestricted* search is the default and take a flag to narrow it to IDs and names, like Chocolatey's `--by-id-only`). Each declared list must pair with a `{exact_args}`-style marker in `args`, standing as its own argument, that expands in place when the refinement is active and to nothing otherwise. `mpm` still refilters the results client-side either way, exactly as for built-in managers.

Any `{token}` in an operation's `args` outside that operation's recognized placeholders is rejected at load time, so a typo like `{qeury}` surfaces immediately instead of reaching the tool as a literal argument.

```{note}
Version pinning is not expressible yet: `install` and `upgrade` on a config-defined manager always let the manager choose the version, and a `{version}` placeholder is not substituted.
```

### Example

```toml
[mpm.managers.deno]
name = "Deno"
platforms = ["linux", "macos", "windows"]
homepage_url = "https://deno.land"
cli_names = ["deno"]
requirement = ">=1.40"
version_regexes = ['deno (?P<version>\S+)']

[mpm.managers.deno.operations.installed]
args = ["list"]
regex = '^(?P<package_id>\S+)@(?P<installed_version>\S+)$'

[mpm.managers.deno.operations.outdated]
args = ["outdated", "--json"]
format = "json"
list_path = "packages"
fields = { package_id = "name", installed_version = "current", latest_version = "latest" }

[mpm.managers.deno.operations.install]
args = ["install", "{package_id}"]

[mpm.managers.deno.operations.upgrade_one]
args = ["install", "--force", "{package_id}"]
```

After this, `mpm --deno installed`, `mpm outdated`, and `mpm install jq --deno` all work, and `--deno` appears in `mpm --help`.

```{tip}
A definition covers managers whose listings parse line-by-line or as a flat JSON array. When the real CLI needs multi-line records, pagination, or stateful parsing, the regex/JSON DSL is not enough: {doc}`write a real manager and upstream it <add-new-manager>` instead.
```

```{note}
mpm ships one such definition itself, as a worked and tested example: [`meta_package_manager/managers/gh_ext.toml`](https://github.com/kdeldycke/meta-package-manager/blob/main/meta_package_manager/managers/gh_ext.toml) defines the `gh-ext` manager (GitHub CLI extensions) using exactly the schema above, and mpm loads it at startup like a built-in. Bundled definitions are the same mechanism as a personal definition, only read from trusted package data instead of your configuration file.
```

## Help improve detection upstream

When an override targets a field that often points to an upstream detection bug, `mpm` prints a one-line invitation to file a bug report so the heuristics can be improved for everyone. The fields that trigger an invitation are: `cli_names`, `cli_search_path`, `requirement`, `version_cli_options`, and `version_regexes`. Overrides on preference fields like `timeout` or `ignore_auto_updates` never trigger an invitation.

The invitation is a pre-filled GitHub new-issue URL targeting the `bug-report.yml` template. Clicking it opens the bug-report form with the manager ID, field, override value, and what `mpm` detected without the override already filled in. The user only has to add the diagnostic command outputs the form requests (`mpm --show-params`, `mpm --verbosity DEBUG --all-managers managers`) before submitting.

To silence the invitation, pass `--no-suggest-contribs` on the command line, set the `MPM_SUGGEST_CONTRIBS` environment variable to `false`, or add to your config file:

```toml
[mpm]
suggest_contribs = false
```

## See also

- {doc}`configuration` — global `[mpm]` settings and configuration-file precedence rules.
- {doc}`security` — the trust model behind overrides and definitions, and why configuration is code.
- {doc}`add-new-manager` — for contributors who want to upstream a new manager rather than override or define one privately.
