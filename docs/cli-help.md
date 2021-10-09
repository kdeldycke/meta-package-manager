# CLI Help Screens

## `mpm`

List global options and commands:

```shell-session
$ mpm --help
Usage: mpm [OPTIONS] COMMAND [ARGS]...

  CLI for multi-package manager upgrades.

Options:
  -m, --manager [apm|apt|apt-mint|brew|cask|choco|composer|flatpak|gem|mas|npm|opkg|pip|snap|vscode|yarn]
                            Restrict sub-command to a subset of package
                            managers. Repeat to select multiple managers. The
                            order in which options are provided defines the
                            order in which sub-commands will process them.
  -e, --exclude [apm|apt|apt-mint|brew|cask|choco|composer|flatpak|gem|mas|npm|opkg|pip|snap|vscode|yarn]
                            Exclude a package manager. Repeat to exclude
                            multiple managers.
  -a, --all-managers        Force evaluation of all package manager implemented
                            by mpm, even those notsupported by the current
                            platform. Still applies filtering by --manager and
                            --exclude options before calling the subcommand.
                            [default: False]
  -x, --xkcd                Forces the subset of package managers to the order
                            defined in XKCD #1654 comic, i.e. ('pip', 'brew',
                            'npm', 'apt').  [default: False]
  --ignore-auto-updates / --include-auto-updates
                            Report all outdated packages, including those tagged
                            as auto-updating. Only applies to 'outdated' and
                            'upgrade' commands.  [default: ignore-auto-updates]
  -o, --output-format [ascii|csv|csv-tab|double|fancy_grid|github|grid|html|jira|json|latex|latex_booktabs|mediawiki|minimal|moinmoin|orgtbl|pipe|plain|psql|psql_unicode|rst|simple|textile|tsv|vertical]
                            Rendering mode of the output.  [default:
                            psql_unicode]
  -s, --sort-by [manager_id|manager_name|package_id|package_name|version]
                            Sort results.  [default: manager_id]
  --stats / --no-stats      Print per-manager package statistics.  [default:
                            stats]
  --time / --no-time        Measure and print elapsed execution time.  [default:
                            no-time]
  --stop-on-error / --continue-on-error
                            Stop right away or continue operations on manager
                            CLI error.  [default: continue-on-error]
  -d, --dry-run             Do not actually perform any action, just simulate
                            CLI calls.  [default: False]
  -C, --config CONFIG_PATH  Location of the configuration file.
  -v, --verbosity LEVEL     Either CRITICAL, ERROR, WARNING, INFO or DEBUG.
                            [default: INFO]
  --version                 Show the version and exit.  [default: False]
  -h, --help                Show this message and exit.  [default: False]

Commands:
  backup     Save installed packages to a TOML file.
  cleanup    Cleanup local data.
  install    Install a package.
  installed  List installed packages.
  managers   List supported package managers and their location.
  outdated   List outdated packages.
  restore    Install packages in batch as specified by TOML files.
  search     Search packages.
  sync       Sync local package info.
  upgrade    Upgrade all packages.
```

## `mpm backup`

```shell-session
$ mpm backup --help
Usage: mpm backup [OPTIONS] [TOML_OUTPUT]

  Dump the list of installed packages to a TOML file.

  By default the generated TOML content is displayed directly in the console
  output. So `mpm backup` is the same as a call to `mpm backup -`. To have the
  result written in a file on disk, specify the output file like so: `mpm backup
  ./mpm-packages.toml`.

  The TOML file can then be safely consumed by the `mpm restore` command.

Options:
  --help  Show this message and exit.  [default: False]
```

## `mpm cleanup`

```shell-session
$ mpm cleanup --help
Usage: mpm cleanup [OPTIONS]

  Cleanup local data and temporary artifacts.

Options:
  --help  Show this message and exit.  [default: False]
```

## `mpm install`

```shell-session
$ mpm install --help
Usage: mpm install [OPTIONS] PACKAGE_ID

  Install the provided package using one of the provided package manager.

Options:
  --help  Show this message and exit.  [default: False]
```

## `mpm installed`

```shell-session
$ mpm installed --help
Usage: mpm installed [OPTIONS]

  List all packages installed on the system from all managers.

Options:
  --help  Show this message and exit.  [default: False]
```

## `mpm managers`

```shell-session
$ mpm managers --help
Usage: mpm managers [OPTIONS]

  List all supported package managers and their presence on the system.

Options:
  --help  Show this message and exit.  [default: False]
```

## `mpm outdated`

```shell-session
$ mpm outdated --help
Usage: mpm outdated [OPTIONS]

  List available package upgrades and their versions for each manager.

Options:
  -c, --cli-format [fragments|plain|xbar]
          Format of CLI fields in JSON output.  [default: plain]
  --help  Show this message and exit.  [default: False]
```

## `mpm restore`

```shell-session
$ mpm restore --help
Usage: mpm restore [OPTIONS] TOML_FILES...

  Read TOML files then install or upgrade each package referenced in them.

  Version specified in the TOML file is ignored in the current implementation.

Options:
  --help  Show this message and exit.  [default: False]
```

## `mpm search`

```shell-session
$ mpm search --help
Usage: mpm search [OPTIONS] QUERY

  Search packages from all managers.

Options:
  --extended / --package-name  Extend search to additional package metadata like
                               description, instead of restricting it package ID
                               and name.  [default: package-name]
  --exact / --fuzzy            Only returns exact matches, or enable fuzzy
                               search in substrings.  [default: fuzzy]
  --help                       Show this message and exit.  [default: False]
```

## `mpm sync`

```shell-session
$ mpm sync --help
Usage: mpm sync [OPTIONS]

  Sync local package metadata and info from external sources.

Options:
  --help  Show this message and exit.  [default: False]
```

## `mpm upgrade`

```shell-session
$ mpm upgrade --help
Usage: mpm upgrade [OPTIONS]

  Perform a full package upgrade on all available managers.

Options:
  --help  Show this message and exit.  [default: False]
```


```{todo}
Dynamiccaly update all CLI output above.
```