# {octicon}`pin` Per-manager overrides

Each built-in manager exposes a small set of attributes that can be overridden from the configuration file. Add a `[mpm.managers.<id>]` section (or `[tool.mpm.managers.<id>]` in `pyproject.toml`) for each manager you want to tune. Values from the file take precedence over the built-in defaults and over the matching global `[mpm]` settings or `--<flag>` command-line values when both apply to the same field.

## Overridable fields

| Field                 | Type             | Description                                                                            |
| :-------------------- | :--------------- | :------------------------------------------------------------------------------------- |
| `cli_names`           | list of strings  | CLI binary names to look for, in order of priority.                                    |
| `cli_search_path`     | list of strings  | Extra directories searched **before** `$PATH` for the binary.                          |
| `deprecated`          | boolean          | Mark a manager as deprecated, hiding it from default selection.                        |
| `dry_run`             | boolean          | Simulate CLI calls without performing any action, only for this manager.               |
| `extra_env`           | table of strings | Additional environment variables passed to every CLI call.                             |
| `ignore_auto_updates` | boolean          | Exclude auto-updating packages from outdated/upgrade results, only for this manager.   |
| `post_args`           | list of strings  | Arguments appended **after** every CLI invocation.                                     |
| `pre_args`            | list of strings  | Arguments inserted **before** every CLI invocation.                                    |
| `pre_cmds`            | list of strings  | Commands prepended to every CLI invocation (typically `sudo`).                         |
| `requirement`         | string           | PEP 440-style version requirement the manager must satisfy to be considered available. |
| `stop_on_error`       | boolean          | Stop on the first CLI error from this manager instead of continuing.                   |
| `timeout`             | integer          | Maximum duration in seconds for each CLI call from this manager.                       |
| `version_cli_options` | list of strings  | CLI options used to extract the manager's reported version.                            |
| `version_regexes`     | list of strings  | Regular expressions tried in order to extract the version from CLI output.             |

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

```{note}
Per-manager overrides apply to existing built-in managers only. Defining brand-new managers from configuration is on the roadmap but not part of this release.
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

- {doc}`configuration` &mdash; global `[mpm]` settings and configuration-file precedence rules.
- {doc}`add-new-manager` &mdash; for contributors who want to upstream a new manager rather than override an existing one.
