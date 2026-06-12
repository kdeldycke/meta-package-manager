# {octicon}`table` JSON & CSV exports

The `installed`, `outdated`, and `search` subcommands render their results as a configurable table. The default is a Unicode-bordered box (`rounded`), but the `--table-format` global option lets you swap in any [serialization format supported by click-extra](https://kdeldycke.github.io/click-extra/table.html#table-formats), including JSON and CSV for downstream piping.

## JSON

```shell-session
$ mpm --table-format json installed > installed_package.json
```

```shell-session
$ jq installed_package.json
```

```json
{
    "pip": {
        "errors": [],
        "id": "pip",
        "name": "Pip",
        "packages": [
            {
                "id": "arrow",
                "installed_version": "1.2.3",
                "name": null
            },
            {
                "id": "boltons",
                "installed_version": "21.0.0",
                "name": null
            }
        ]
    },
    "vscode": {
        "errors": [],
        "id": "vscode",
        "name": "Visual Studio Code",
        "packages": [
            {
                "id": "charliermarsh.ruff",
                "installed_version": "2023.6.0",
                "name": null
            },
            {
                "id": "ExecutableBookProject.myst-highlight",
                "installed_version": "0.11.0",
                "name": null
            },
            {
                "id": "GitHub.copilot",
                "installed_version": "1.73.8685",
                "name": null
            }
        ]
    },
}
```

The JSON output is grouped by manager. Each manager block carries an `errors` array so callers can detect partial failures without scraping stderr.

## CSV

```shell-session
$ mpm --table-format csv installed > installed_package.csv
```

```shell-session
$ cat installed_package.csv
```

```csv
Package ID,Name,Manager,Installed version
arrow,,pip,1.2.3
boltons,,pip,21.0.0
charliermarsh.ruff,,vscode,2023.6.0
ExecutableBookProject.myst-highlight,,vscode,0.11.0
GitHub.copilot,,vscode,1.73.8685
```

CSV flattens the per-manager grouping into one row per package, with `Manager` as a column.

## Accessibility

For screen readers, pass `--accessible` (or set `ACCESSIBLE=1` in the environment) to strip ANSI colors and replace the Unicode box-drawing characters with plain `+--` / `|` separators. This switch is independent of `--table-format`: `mpm --accessible --table-format json installed` still emits JSON, just without color codes interleaved in log messages.

## See also

- {doc}`dump` &mdash; richer TOML and Brewfile snapshots that preserve manager structure for replay.
- {doc}`sbom` &mdash; SPDX/CycloneDX exports targeted at supply-chain inventory work rather than ad-hoc piping.
