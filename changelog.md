# Changelog

## {gh}`5.4.0 (unreleased) <compare/v5.3.0...main>`

```{important}
This version is not released yet and is under active development.
```

- \[mpm\] Allow global `upgrade` of a subset of packages from the command line.
- \[mpm\] Add a `-A`/`--all` option to `upgrade` operation.
- \[mpm\] add a `-d`/`--duplicates` option to `installed` operation to only show packages sharing the same ID accross multiple managers.
- \[mpm\] Add a global `--description` option but implement it for `search` operation only.
- \[mpm\] Always show description for `--extended` search. Closes {issue}`503`.
- \[mpm\] Rename `--package-name` search option to `--id-name-only`.
- \[mpm\] Add operation aliases:
  - `list` → `installed`
  - `uninstall` → `remove`
  - `update` → `upgrade`
  - `lock`/`freeze`/`snapshot` → `backup`
- \[mpm\] Add a `--merge` option on `backup` operation to update target TOML file with new installed packages.
- \[mpm\] Add an `--update-version` option on `backup` operation to only update version in the target TOML file.
- \[mpm\] Add a `--overwrite`/`--force`/`--replace` option on `backup` operation to force TOML overwrite if destination file exists.
- \[pipx\] Implement `outdated` operation.
- \[pip\] Do not wait for user confirmation on `remove` operation.
- \[mpm\] Rename all `*-like` labels to `*-based` to help finer identification of families.

## {gh}`5.3.0 (2022-06-25) <compare/v5.2.0...v5.3.0>`

- \[paru\] Add `paru` support.
- \[pacman,paru,yay\] Run `install`, `upgrade`, `remove` and `cleanup` operations with `sudo`.
- \[brew,cask\] Implement extended search on description.
- \[cargo\] Implement `remove` operation.
- \[mas\] Fix parsing of variable-length output in `installed` and `outdated` operations.
- \[npm\] Apply global variables to all operations.
- \[bar-plugin\] Fix rendering of package managers without outdated packages. Closes {issue}`631`.
- \[mpm\] Colorize version differences in `outdated` operation output.
- \[mpm\] Add manager homepage URL metadata.
- \[mpm\] Keep results matching description in `--extended` search mode.
- \[mpm\] Simplify `installed`, `outdated` and `search` operation by relying on generators and a `package` dataclass.
- \[mpm\] Disable workflow grouping and concurrency management.

## {gh}`5.2.0 (2022-06-16) <compare/v5.1.0...v5.2.0>`

- \[yay\] Add `yay` support. Refs {issue}`527`.
- \[mpm,pip,pipx,pacman\] Add `remove` operation.
- \[mpm\] Add description in search results. Refs {issue}`503`.
- \[mpm\] Always refilters search results manually to refine gross matchings.
- \[mpm\] Document `brew` and Arch Linux installation. Refs {issue}`527`.
- \[mpm\] Benchmark distribution of all `mpm` alternatives.
- \[mpm\] Group workflow jobs so new commits cancels in-progress execution triggered by previous commits.
- \[mpm\] Run tests on early Python 3.11 releases.

## {gh}`5.1.0 (2022-05-15) <compare/v5.0.1...v5.1.0>`

- \[pipx\] Add `pipx` support. Closes {issue}`468`.
- \[cargo\] Add `cargo` support. Closes {issue}`633`.
- \[mpm\] Factorize search result refiltering code.
- \[mpm\] Regroup `dnf` and `yum` labels.

## {gh}`5.0.1 (2022-04-28) <compare/v5.0.0...v5.0.1>`

- \[apt\] Fix commands incompatible with `--yes` option. Closes {issue}`625`.
- \[mpm\] Add `topgrade` and `pacaptr` in the list of benchmarked alternatives.
- \[mpm\] Rename `alternative` page to `benchmark`.
- \[mpm\] Fix label unittests.

## {gh}`5.0.0 (2022-04-25) <compare/v4.13.1...v5.0.0>`

- \[zypper\] Add `zypper` support for Suse and OpenSuse. Closes {issue}`566`.
- \[emerge\] Add `emerge` support.
- \[steamcmd\] Add `steamcmd` support. Refs {issue}`10`.
- \[yum\] Add dedicated `yum` package manager. Refs {issue}`415`.
- \[bar-plugin\] Add new `DEFAULT_FONT` and `MONOSPACE_FONT` variable.
- \[bar-plugin\] Rename all reference of `xbar` to the generic `bar-plugin` label.
- \[bar-plugin\] Improve search for Python and `mpm` executable.
- \[bar-plugin\] Restructure the plugin ↔ mpm relationship to delegate all
  plugin layout and rendering logic to `mpm`.
- \[bar-plugin\] Prevent leaks when modifying environment variables.
- \[mpm\] Allow `installed` and `outdated` commands to be optionally
  implemented by package managers.
- \[mpm\] Add new `--plugin-output` option to `outdated` command.
- \[mpm\] Add `tabulate` as direct dependency and refactor table aligment in
  plugin around it.
- \[mpm\] Rename `--xbar-plugin-path` option to `--bar-plugin-path`.
- \[mpm\] Remove `-c`/`--cli-format` option.
- \[mpm\] Use short-form selection option and fully-qualified path in
  `mpm`-based upgrade-all CLIs produced by `outdated` command.
- \[mpm\] Add dedicated execution path for running sudo-prefixed commands.
- \[mpm\] Fix local overriding of CLI parameters leading to missing `sudo`
  pre-command. Closes {issue}`579`.
- \[mpm\] Use string highlighting code from `click-extra >= 2.1.0`.
- \[mpm\] Add edit links to documentation.

## {gh}`4.13.1 (2022-04-17) <compare/v4.13.0...v4.13.1>`

- \[apt\] Add missing `sudo` pre-commands for `apt` calls that requires it.
  Closes {issue}`496` and {issue}`579`.
- \[snap\] Fix command argument order. Address {issue}`579`.
- \[bar-plugin\] Fix location of `mpm` binary on Apple Silicon machines.
- \[mpm\] Replace `sphinx_tabs` by `sphinx-design`.
- \[mpm\] Add SwiftBar plugin screenshots.
- \[mpm\] Remove date-based shallowing of Homebrew git repository in unittests
  and considers the local runner copy to already be unshallowed.

## {gh}`4.13.0 (2022-04-16) <compare/v4.12.1...v4.13.0>`

- \[pacman\] Add support for `pacman`. Closes {issue}`416`.
- \[apt-mint\] Fix search. Closes {issue}`572` and {pr}`573`.
- \[apt-mint\] Fix `--apt-mint` shortcut option.
- \[bar-plugin\] Add support for SwiftBar.
- \[bar-plugin\] Add new `TABLE_RENDERING` option to plugin.
- \[bar-plugin\] Improve alignment of labels in monospaced font rendering.
- \[bar-plugin\] Tweak icons.
- \[mpm\] Allow the `meta_package_manager` module to be directly executed.
- \[mpm\] Add `--xbar-plugin-path` option.
- \[mpm\] Fix normalization of CLI arguments.
- \[mpm\] Fix file not found error on non-Windows platform during version checking.

## {gh}`4.12.1 (2022-04-05) <compare/v4.12.0...v4.12.1>`

- \[mpm\] Make CLI path evaluation more robust on Windows. Closes {issue}`542`.

## {gh}`4.12.0 (2022-04-04) <compare/v4.11.0...v4.12.0>`

- \[dnf\] Add support for `dnf`. Closes {issue}`516`, refs {issue}`415`.
- \[yum\] Allow `yum` to act as `dnf`. Closes {issue}`415`.
- \[brew,cask\] Fix execution of `sync` command.
- \[mpm\] Fix extraction of version. Closes {issue}`536`.

## {gh}`4.11.0 (2022-04-03) <compare/v4.10.0...v4.11.0>`

- \[brew,cask\] Do not let homebrew auto-update on other commands. Refs {issue}`36`.
- \[brew,cask\] Disable analytics and env hints in logs.
- \[bar-plugin\] Fix log verbosity and unittests for xbar plugin.
- \[mpm\] Show in debug logs the extra environment variable used for CLIs.
- \[mpm\] Enforce code structure in package manager definition files.
- \[mpm\] Fix documentation generation.

## {gh}`4.10.0 (2022-03-31) <compare/v4.9.10...v4.10.0>`

- \[mpm\] Allow for package managers to simultaneously set a list of
  pre-commands and environment variables, as well as global arguments before
  and after the custom ones.
- \[mpm\] Always run unittest in parrallel. Adds development dependency on
  `pytest-xdist` and `psutil`.
- \[mpm\] Use the `tomllib` from the standard library starting with Python
  3.11.
- \[mpm\] Cap `click-extra` requirement to `<1.7.0` to fix regression. Closes
  {issue}`518`.

## {gh}`4.9.10 (2022-03-09) <compare/v4.9.9...v4.9.10>`

- \[mpm\] Fix execution error on Python 3.10 by updating `click-extra`. Closes
  {issue}`467`.
- \[mpm\] Reactivate all unittests on Python 3.10.
- \[mpm\] Remove artifial capping of Python 3.9 to some workflows.
- \[mpm\] Use external workflow for dependency graph generation and Python code
  modernization.
- \[mpm\] Remove direct dependency on `cloup`, `simplejson` and `pipdeptree`.

## {gh}`4.9.9 (2022-01-15) <compare/v4.9.8...v4.9.9>`

- \[mpm\] Fix upload of build artefacts in GitHub release.

## {gh}`4.9.8 (2022-01-15) <compare/v4.9.7...v4.9.8>`

- \[mpm\] Fix propagation of build artefacts to GitHub release and PyPi.
- \[mpm\] Fix test of labelling rules.
- \[mpm\] Remove local dependency on `graphviz` now that fixes were pushed
  upstream.

## {gh}`4.9.7 (2022-01-11) <compare/v4.9.6...v4.9.7>`

- \[mpm\] Add release version in artefacts produced by Poetry builds.
- \[mpm\] Pass local PyPi token to reused workflow to fix publishing.

## {gh}`4.9.6 (2022-01-11) <compare/v4.9.5...v4.9.6>`

- \[mpm\] Fix detection of Poetry in build workflow.

## {gh}`4.9.5 (2022-01-11) <compare/v4.9.4...v4.9.5>`

- \[mpm\] Use external workflow for package building and publishing via Poetry.
- \[mpm\] Reused external label maintainance workflows and definitions.
- \[mpm\] Add our custom labels to external syncing workflow.
- \[mpm\] Auto-label sponsors.
- \[mpm\] Remove changelog code left-overs.
- \[mpm\] Aligns content of all PRs locally produced by workflows.

## {gh}`4.9.4 (2022-01-04) <compare/v4.9.3...v4.9.4>`

- \[mpm\] Re-integrate artefacts in GitHub release on tagging.

## {gh}`4.9.3 (2022-01-04) <compare/v4.9.2...v4.9.3>`

- \[mpm\] Fix GitHub release's content update.

## {gh}`4.9.2 (2022-01-04) <compare/v4.9.1...v4.9.2>`

- \[mpm\] Regenerate GitHub release content body dynamiccaly on tagging.

## {gh}`4.9.1 (2022-01-04) <compare/v4.9.0...v4.9.1>`

- \[mpm\] Automate minor and major version bump.
- \[mpm\] Automate release preparation workflow.
- \[mpm\] Trigger tagging, build and version bump on release event.
- \[mpm\] Add a debug workflow for troubleshooting.

## {gh}`4.9.0 (2022-01-03) <compare/v4.8.0...v4.9.0>`

- \[mpm\] Add single manager selector aliases: `--apm`, `--apt`, `--apt-mint`,
  `--brew`, `--cask`. `--choco`, `--composer`, `--flatpak`, `--gem`, `--mas`,
  `--npm`, `--opkg`, `--pip`, `--snap`, `--vscode` and `--yarn`.
- \[brew,cask\] Thorough cleanup: call `autoremove` commands to remove unused
  dependencies and use `--prune=all` to scrub the whole cache.
- \[mpm\] Switch default table rendering to `rounded_outline`.
- \[mpm\] Rely on `click-extra` for table rendering and tests.
- \[mpm\] Remove direct dependencies on `click-log` and `cli-helpers`.
- \[mpm\] Automate post-release version bump.
- \[mpm\] Outsource some workflow definition to external repository.
- \[mpm\] Fix generation of dependency graph.

## {gh}`4.8.0 (2021-11-01) <compare/v4.7.0...v4.8.0>`

- \[mpm\] Add `--color`/`--no-color` (aliased to `--ansi`/`--no-ansi`) flags.
- \[mpm\] Forces no color on JSON output.
- \[mpm\] Group commands and options in help screen.
- \[mpm\] Colorize options, choices, metavars and default values in help
  screens.
- \[mpm\] Reintroduce coloring of `--version` option.
- \[mpm\] Add dependency on `click-extra`.
- \[mpm\] Use `sphinx-click` to auto-generate CLI documentation.
- \[mpm\] Autofix Markdown content with `mdformat`.
- \[mpm\] Simplify project management by abandoning the dual use of
  `main`/`develop` branches.

## {gh}`4.7.0 (2021-10-13) <compare/v4.6.0...v4.7.0>`

- \[mpm\] Add help screen coloring.
- \[mpm\] Change documentation theme from classic RTD to furo.
- \[mpm\] Move documentation from `readthedocs.org` to `github.io`.
- \[mpm\] Rewrite documentation from rST to MyST.
- \[mpm\] Add dependency on `cloup`.
- \[mpm\] Removes `click-help-colors` dependency.
- \[mpm\] Run tests on Python 3.10.
- \[mpm\] Add a contribution guide stub in documentation. Closes {issue}`276`.

## {gh}`4.6.0 (2021-10-04) <compare/v4.5.0...v4.6.0>`

- \[mpm\] Implements XKCD 1654. Closes {issue}`10`.
- \[mpm\] Add `-x`/`--xkcd` option to forces manager selection.
- \[mpm\] Let `-m`/`--manager` multi-option keep order.

## {gh}`4.5.0 (2021-09-30) <compare/v4.4.0...v4.5.0>`

- \[choco\] Add Chocolatey package manager.
- \[mpm\] Skip by default the evaluation of package managers not supported on
  the user's platform. Closes {issue}`278`.
- \[mpm\] Add a `-a`/`--all-managers` option to force the evaluation of all
  managers.
- \[mpm\] Fix highlighting of substrings in search results.

## {gh}`4.4.0 (2021-09-27) <compare/v4.3.0...v4.4.0>`

- \[mpm\] Add a global `-d`/`--dry-run` option.
- \[apt\] Add dedicated `apt-mint` manager to handle the special case of `apt`
  on Linux Mint.
- \[bar-plugin\] Let xbar plugin check minimal mpm version requirement.
- \[mpm\] Use regexpes to extract package manager versions.
- \[mpm\] Add beta `windows-2022` CI/CD build target.
- \[mpm\] Remove all the unused utilities to discard some table rendering on
  Windows.

## {gh}`4.3.0 (2021-09-25) <compare/v4.2.0...v4.3.0>`

- \[mpm\] Add new `install` command. Closes {issue}`21`.
- \[vscode\] Add support for Visual Studio Code plugins.
- \[mpm\] Finish complete `restore` command implementation. Closes {issue}`38`.
- \[mpm\] Remove un-enforced poetry-like caret-based version specifiction from
  TOML backup files.
- \[mpm\] Forces logger state reset before each CLI call in unittests.

## {gh}`4.2.0 (2021-09-21) <compare/v4.1.0...v4.2.0>`

- \[mpm\] Add support for TOML configuration file. Closes {issue}`66`.
- \[mpm\] Add `-C`/`--config` option to point to specific configuration file.
- \[mpm\] Upgrade to Click 8.x.
- \[mpm\] Add support for `psql_unicode` and `minimal` table format.
- \[mpm\] Set default table format to `psql_unicode` instead of `fancy_grid` to
  reduce visual noise.
- \[mpm\] Add support for environment variables for all parameters, prefixed
  with `MPM_`.
- \[mpm\] Let Click produce default values in help screen.
- \[mpm\] Replace `tomlkit` dependency by `tomli` and `tomli_w`.
- \[bar-plugin\] Fix xbar plugin output format.
- \[bar-plugin\] Rename `VAR_SUBMENU_lAYOUT` environment variable to
  `VAR_SUBMENU_LAYOUT`.
- \[mpm\] Remove support for `--cli-format bitbar` option. Use `xbar` value
  instead.

## {gh}`4.1.0 (2021-05-01) <compare/v4.0.0...v4.1.0>`

- \[bar-plugin\] Add new `Submenu layout` boolean option in xbar plugin UI.
- \[bar-plugin\] Rename `XBAR_MPM_SUBMENU` environment variable to
  `VAR_SUBMENU_lAYOUT`.
- \[mpm\] Allow search of multiple CLI names for a package manager.
- \[pip\] Fix search of `python3` binary on macOS. Closes {issue}`247`.

## {gh}`4.0.0 (2021-04-27) <compare/v3.6.0...v4.0.0>`

- \[bar-plugin\] Upgrade BitBar plugin to new xbar format.
- \[bar-plugin\] Drop xbar plugin requirement on Python 2.x and bump it up to Python
  3.7.3.
- \[bar-plugin\] Update references of BitBar to xbar.
- \[bar-plugin\] Rename `BITBAR_MPM_SUBMENU` environment variable to
  `XBAR_MPM_SUBMENU`.
- \[mpm\] Rename `--cli-format bitbar` option to `--cli-format xbar`.
- \[mpm\] Auto-generate API documentation via a GitHub action workflow.
- \[mpm\] Only trigger dependency graph update on tagging to reduce noise.
- \[mpm\] Re-introduce `isort`.

## {gh}`3.6.0 (2021-01-03) <compare/v3.5.2...v3.6.0>`

- \[brew\] Add support for `brew` on Linux.
- \[brew,cask\] Bump minimal requirement of `brew` to `2.7.0`.
- \[cask\] Address deprecation of `cask` CLI subcommands.
- \[pip\] `pip search` has been disabled by maintainers because of server-side
  high-load.
- \[mpm\] Add test runs against new OSes and distributions: `ubuntu-18.04` and
  `macos-11.0`.
- \[mpm\] Remove `pycodestyle` now that we rely on `black`.
- \[mpm\] Add emoji to issue labels.

## {gh}`3.5.2 (2020-10-29) <compare/v3.5.1...v3.5.2>`

- \[mpm\] Run tests on Python 3.9.
- \[mpm\] Upgrade to `Poetry 1.1.0`.
- \[mpm\] Colorize version screen and add debug data.
- \[mpm\] Test publishing to PyPi in dry-run mode by the way of Poetry.
- \[mpm\] Make all keyword-based choice parameters (`--manager`, `--exclude`,
  `--output-format`, `--sort-by` and `--cli-format`) case-insensitive.
- \[mpm\] Pin versions of OSes and distributions in CI workflows to
  `ubuntu-20.04`, `macos-10.15` and `windows-2019`.
- \[mpm\] Always print errors in unittest's CLI calls.
- \[mpm\] Slow-down tests to prevent PyPi rate-limiting on live API.
- \[mpm\] Fix `brew` setup on macOS CI runners.
- \[mpm\] Fix `npm` setup in Ubuntu 18.04 and 20.04 CI runners.
- \[mpm\] Use latest `Atom` version in Ubuntu CI runners.

## {gh}`3.5.1 (2020-10-03) <compare/v3.5.0...v3.5.1>`

- \[mpm\] Defaults to `--continue-on-error` instead of stopping.
- \[mpm\] Force checking of CLI being a file.
- \[mpm\] Auto-optimize images.
- \[mpm\] Auto-lock closed issues and PRs after a moment of inactivity.

## {gh}`3.5.0 (2020-09-20) <compare/v3.4.2...v3.5.0>`

- \[mpm\] Fix `--stop-on-error` parameter: it was never taken into account.
- \[brew,cask\] Bump minimal requirement of `brew` to `2.5.0`.
- \[brew,cask\] Fix warning to deprecated options.
- \[npm\] Always fix JSON parsing on error for any npm subcommand.

## {gh}`3.4.2 (2020-09-13) <compare/v3.4.1...v3.4.2>`

- \[brew,cask\] Do not mix-up brew and cask upgrades.
- \[npm\] Skip parsing of JSON results on error.

## {gh}`3.4.1 (2020-09-02) <compare/v3.4.0...v3.4.1>`

- \[mpm\] Rename `master` branch to `main`.

## {gh}`3.4.0 (2020-08-18) <compare/v3.3.0...v3.4.0>`

- \[yarn\] Set minimal requirement to 1.20.0.
- \[yarn\] Fix deprecated global arguments.
- \[bar-plugin\] Force refresh of local package databases before fetching outdated
  ones.
- \[mpm\] Add utilities to read a config TOML file. Refs {issue}`66`.
- \[mpm\] Auto-format Python code with Black.
- \[mpm\] Move `pytest` config from `setup.py` to `pyproject.toml`.
- \[mpm\] Removes `isort`.
- \[mpm\] Auto-update Python's dependencies.
- \[mpm\] Auto-update GitHub actions.
- \[mpm\] Auto-update `.gitignore` file.
- \[mpm\] Auto-update `.mailmap` file.
- \[mpm\] Lint all YAML files. Add dependency on `yamllint` package.
- \[mpm\] Removes `requires.io` and Scrutinizer badges.
- \[mpm\] Revert to `pipdeptree` to produce package dependency graph.

## {gh}`3.3.0 (2020-06-23) <compare/v3.2.0...v3.3.0>`

- \[bar-plugin\] Each entry in the drop-down menu can now be called into a terminal
  to track the execution by holding the `Option` key.
- \[bar-plugin\] Fix rendering of upgrade CLI in Bitbar dialect.
- \[mpm\] Hint for lack of `sync` and `cleanup` support by managers.
- \[mpm\] Do not print table headers if there is no row to print.
- \[mpm\] Always print non-fatal `<stderr>` output as warning mode.
- \[mpm\] Skip table rendering tests if no table is printed to stdout. Fixes
  flacky tests.
- \[mpm\] Replace internal helpers with upstreamed `boltons 20.2.0` utils.
- \[mpm\] Force test marked as `xfail` count as failure if they succeed.
- \[mpm\] Always check wheel content.
- \[mpm\] Automate creation of GitHub release.
- \[mpm\] Automate publishing of package to PyPi on tagging.
- \[mpm\] Save build artifacts on each CI runs.
- \[mpm\] Auto-sort module imports.
- \[mpm\] Auto-fix common typos.
- \[mpm\] Lint JSON files.
- \[mpm\] Automate GitHub label generation and synchronization.
- \[mpm\] Automatically applies labels on PRs and issues depending on their
  changed files and content.
- \[mpm\] Check label rules against manager definitions. Adds development
  dependency on `PyYAML`.

## {gh}`3.2.0 (2020-05-31) <compare/v3.1.0...v3.2.0>`

- \[snap\] Add support for `snap` on Linux.
- \[cask\] Rely on JSON output to fetch outdated packages.
- \[brew,cask\] Bump minimal requirement to 2.2.15.
- \[pip\] Remove `pip2`/`pip3` distinctions, use system's python and call `pip`
  module.
- \[windows\] Allow discarding of some table rendering on Windows.
- \[mpm\] Add `--time`/`--no-time` flag to show elapsed execution time. Closes
  {issue}`9`.
- \[mpm\] Print table rendering, stats and timing in console output instead of
  logger to allow them to be greppable.
- \[bar-plugin\] Test plugin with Python 2.7.
- \[mpm\] Allow for manager-specific search path to help hunting down CLIs.
- \[mpm\] Highlight CLI and indent results in debug output.
- \[mpm\] Bump dependency to `pylint 2.5` and `cli-helpers 2.0`.
- \[mpm\] Use local copy of `boltons` utils while we wait for upstream release.
- \[mpm\] Move pylint config from `setup.cfg` to `pyproject.toml`.
- \[mpm\] Fail CI and QA checks if pylint score lower than 9.
- \[mpm\] Add more platform definition unittests.
- \[mpm\] Unittests all rendering modes in all subcommands.
- \[mpm\] Randomize unittests.
- \[mpm\] Drop support of Python 3.6.
- \[mpm\] Use group-tabs in Sphinx docs.

## {gh}`3.1.0 (2020-04-02) <compare/v3.0.0...v3.1.0>`

- \[mpm\] Add new `cleanup` command. Closes {issue}`5`.
- \[mpm\] Improve table sorting with new version-aware tokenizer.
- \[mpm\] Highlight manager IDs depending on their availability in `managers`
  command.
- \[gem\] Ignore `default:` prefix on package version parsing.
- \[mpm\] Remove `packaging` dependency. Rely on internal version parsing.
- \[mpm\] Add new `--exact` and `--extended` parameters to `search` command.
- \[mpm\] Highlight search matches in console output.
- \[mas\] Retrieve version in search results.
- \[mas\] Bump minimal version to `1.6.1`.
- \[mpm\] Allow stats to be printed for `backup` command.
- \[gem\] Bump minimal requirement to `2.5.0`.

## {gh}`3.0.0 (2020-03-25) <compare/v2.9.0...v3.0.0>`

- \[mpm\] Add new `backup` and dummy `restore` commands to respectively dump
  and load up list of installed packages to/from a TOML file. Refs {issue}`38`.
- \[mpm\] Add dependency on `tomlkit`.
- \[yarn\] Add support for `yarn` package manager for Linux, macOS and Windows.
- \[yarn\] Install yarn on all unittest platforms.
- \[mpm\] Allow exclusion of a subset of package managers. Closes {issue}`45`.
- \[pip\] Collect installer metadata on listing.
- \[pip\] Bump minimal requirement of `pip` to `10.0.*`.
- \[mpm\] Prepend `/usr/local/bin` to cli search path.
- \[npm\] `install package@version` instead of `update package`.
- \[npm\] Skip update notifier.
- \[brew,cask\] Allow independent search for each manager.
- \[brew,cask\] Bump minimal requirement of to `2.2.9`.
- \[mpm\] Allow sorting restuls by packages, managers or version. Closes
  {issue}`35` and {pr}`37`.
- \[mpm\] Add shell completion for Bash, Zsh and Fish.
- \[mpm\] Do not force sync when calling outdated. Closes {issue}`36`.
- \[apt\] Fallback on `apt version apt` when looking for version. Closes
  {pr}`57` and {issue}`52`.
- \[mpm\] Removes all copyright dates.
- \[mpm\] Replace unmaintained `bumpversion` by `bump2version`.
- \[mpm\] Raise requirement to `click 7.1`.
- \[mpm\] Raise requirement to `boltons >= 20.0`.

## {gh}`2.9.0 (2020-03-18) <compare/v2.8.0...v2.9.0>`

- \[mpm\] Drop support of Python 2.7, 3.4 and 3.5. Add support for Python 3.8.
- \[windows\] Add support for `apm`, `composer`, `gem`, `npm` and `pip2` on
  Windows.
- \[linux\] Add support for `Flatpak` and `opkg` package managers on Linux.
- \[gem\] Force Ruby `gem` to install packages to user-install by default. Refs
  {issue}`58`.
- \[pip\] Force Python `pip` upgrade to user-installed packages. Refs {pr}`58`.
- \[brew\] Fix call to `brew upgrade --cleanup`. Refs {issue}`50`.
- \[brew\] Fix parsing of `brew` version. Closes {issue}`49` and {pr}`51`.
- \[mpm\] Switch from Travis to GitHub actions.
- \[composer\] Install `composer` in all platforms CI runners.
- \[linux\] Install `flatpak` in Linux CI runner.
- \[windows\] Install `apm` in Windows CI runner.
- \[mpm\] Bump requirement to `click-log >= 0.3`.
- \[mpm\] Add non-blocking Pylint code quality checks in CI.
- \[mpm\] Check for conflicting dependencies in CI.
- \[mpm\] Use Poetry for package and virtualenv management.
- \[mpm\] Replace `pipdeptree` by Poetry CLI output.
- \[mpm\] Remove `backports.shutil_which` dependency.
- \[mpm\] Update `.gitignore`.
- \[mpm\] Drop all Python 3.0 `__future__` imports.
- \[mpm\] Add detailed usage CLI page in documentation.

## {gh}`2.8.0 (2019-01-03) <compare/v2.7.0...v2.8.0>`

- \[composer\] Add support for PHP `composer`.
- \[cask\] Remove `cask`-specific `version`, `sync` and `search` command.
  Closes {issue}`47`.
- \[brew\] Vanilla brew and cask CLIs now shares the same version requirements.
- \[brew\] Bump minimal requirement of `brew` and `cask` to `1.7.4`.
- \[mpm\] Activate unittests in Python 3.7.
- \[mpm\] Drop Travis unittests on deprecated Ubuntu Precise targets and
  vintage Mac OS X 10.10 and 10.11.
- \[mpm\] Use latest macOS 10.12 and 10.13 Travis images.

## {gh}`2.7.0 (2018-04-02) <compare/v2.6.1...v2.7.0>`

- \[mpm\] Add new `--ignore-auto-updates` and `--include-auto-updates` boolean
  flags.
- \[mpm\] Support even fancier table output rendering, including `csv` and
  `html`.
- \[mpm\] Depends on `cli-helpers` package to render tables.
- \[mpm\] Removes direct dependency on `tabulate`.
- \[cask\] Fix minimal version check for `cask`. Closes {issue}`41` and
  {pr}`44`.
- \[bar-plugin\] Do not run BitBar plugin unittests but on macOS.

## {gh}`2.6.1 (2017-11-05) <compare/v2.6.0...v2.6.1>`

- \[mpm\] Fix Travis unittests.

## {gh}`2.6.0 (2017-09-11) <compare/v2.5.0...v2.6.0>`

- \[apt\] Add support for `apt` on Linux systems.
- \[pip\] Use pip 9.0 JSON output. Closes {issue}`18`.
- \[pip\] Bump minimal requirement of `pip` to `9.0.*`.
- \[cask\] Use new `brew cask outdated` command.
- \[cask\] Remove usage of deprecated `brew cask update` command.
- \[cask\] Bump minimal requirement of `cask` to `1.1.12`.
- \[mpm\] Add dependency on `simplejson`.
- \[mpm\] Bump requirement to `click_log >= 0.2.0`. Closes {issue}`39`.
- \[mpm\] Replace `nose` by `pytest`.
- \[mpm\] Only notify by mail of test failures.

## {gh}`2.5.0 (2017-03-01) <compare/v2.4.0...v2.5.0>`

- \[mpm\] Auto-detect location of manager CLI on the system.
- \[mpm\] Add new `search` operation. Closes {issue}`22`.
- \[npm\] Bump minimal requirement of `npm` to `4.0.*`.
- \[mpm\] Rename `list` operation to `installed`.
- \[gem,npm,apm,linux\] Allow use of `gem`, `npm` and `apm` managers on Linux.
- \[mpm\] Add new `--stats`/`--no-stats` boolean flags. Closes {issue}`8`.
- \[mpm\] Add new `--stop-on-error`/`--continue-on-error` parameters to make
  CLI errors either blocking or non-blocking.
- \[mpm\] Allow reporting of several CLI errors by managers.
- \[mpm\] Allow selection of a subset of managers.
- \[mpm\] Do not force a `sync` before listing installed packages in CLI.
- \[mpm\] Rework API documentation.
- \[cask\] Add unittest to cover unicode names for Cask packages. Closes
  {issue}`16`.
- \[cask\] Add unittest to cover Cask packages with multiple names. Refs
  {issue}`26`.
- \[mpm\] Drop support of Python 3.3.

## {gh}`2.4.0 (2017-01-28) <compare/v2.3.0...v2.4.0>`

- \[mpm\] Add new `list` operation. Closes {issue}`20`.
- \[mas\] Fix upgrade of `mas` packages. Closes {issue}`32`.
- \[bar-plugin\] Document BitBar plugin release process.
- \[mpm\] Colorize check-marks in CLI output.
- \[mpm\] Decouple `sync` and `outdated` actions in all managers.
- \[mpm\] Cache output of `outdated` command.
- \[mpm\] Add global todo list in documentation.
- \[mpm\] Bump requirement to `boltons >= 17.0.0` for Python 3.3 compatibility.

## {gh}`2.3.0 (2017-01-15) <compare/v2.2.0...v2.3.0>`

- \[mpm\] Add Sphinx documentation. Closes {issue}`24`.
- \[mpm\] Add installation instructions. Closes {issue}`19`.
- \[mpm\] Add a list of *Falsehoods Programmers Believe About Package
  Managers*.
- \[mpm\] Add a `.mailmap` config file to consolidate contributor's identity.
- \[bar-plugin\] Make it easier to change the font, size and color of text in
  BitBar plugin.
- \[bar-plugin\] Move error icon in BitBar plugin to the front of manager name.
- \[cask\] Fix parsing of `cask` packages with multiple names. Closes
  {issue}`26`.
- \[bar-plugin\] Move BitBar plugin documentation to dedicated page.
- \[mpm\] Fix exceptions when commands gives no output. Closes {issue}`29` and
  {pr}`31`.
- \[cask\] Fix `cask update` deprecation warning. Closes {issue}`28`.
- \[mpm\] Activate unittests in Python 3.6.
- \[mpm\] Replace double by single-width characters in `mpm` output to fix
  table misalignement. Closes {issue}`30`.

## {gh}`2.2.0 (2016-12-25) <compare/v2.1.1...v2.2.0>`

- \[mpm\] Rename `supported` property of managers to `fresh`.
- \[mpm\] Allow restriction of package managers to a platform. Closes
  {issue}`7`.
- \[mpm\] Include `supported` property in `mpm managers` sub-command.
- \[bar-plugin\] Add optional submenu rendering for BitBar plugin. Closes {pr}`23`.
- \[bar-plugin\] Move `Upgrade all` menu entry to the bottom of each section in
  BitBar plugin.
- \[pip\] Allow destructive unittests in Travis CI jobs.
- \[pip\] Allow usage of `pip2` and `pip3` managers on Linux.
- \[mpm\] Print current platform in debug messages.
- \[mpm\] Unittest detection of managers on each platform.

## {gh}`2.1.1 (2016-12-17) <compare/v2.1.0...v2.1.1>`

- \[brew,cask\] Fix parsing of non-point releases of `brew` and `cask`
  versions. Closes {issue}`15`.
- \[bar-plugin\] Do not render emoji in BitBar plugin menu entries.
- \[bar-plugin\] Do not trim error messages rendered in BitBar plugin.
- \[mpm\] Do not strip CLI output. Keep original format.
- \[mpm\] Fix full changelog link.

## {gh}`2.1.0 (2016-12-14) <compare/v2.0.0...v2.1.0>`

- \[bar-plugin\] Adjust rendering of BitBar plugin errors.
- \[mpm\] Fix fetching of log level names in Python 3.4+.
- \[mpm\] Print CLI output in unittests.
- \[mpm\] Print more debug info in unittests when CLI produce tracebacks.
- \[macos\] Drop support and unittests on Mac OS X 10.9.
- \[macos\] Add new macOS 10.12 target for Travis CI builds.
- \[bar-plugin\] Move BitBar plugin within the Python module.
- \[mpm\] Show unmet version requirements in table output for `mpm managers`
  sub-command.
- \[mpm\] Fix duplicates in outdated packages by indexing them by ID.
- \[bar-plugin\] Unittest simple call of BitBar plugin.
- \[mpm\] Always print the raw, un-normalized version of managers, as reported
  by themselves.
- \[mpm\] Fetch version of all managers.
- \[mpm\] Make manager version mandatory.
- \[mpm\] Bump requirement to `readme_renderer >= 16.0`.
- \[mpm\] Always remove ANSI codes from CLI output.
- \[mpm\] Fix rendering of unicode logs.
- \[mpm\] Bump requirement to `click_log >= 0.1.5`.
- \[bar-plugin\] Force `LANG` environment variable to `en_US.UTF-8`.
- \[mpm,bar-plugin\] Share same code path for CLI execution between `mpm` and
  BitBar plugin.
- \[mpm\] Add a `-d`/`--dry-run` option to `mpm upgrade` sub-command.
- \[macos\] Remove hard-requirement on `macOS` platform. Refs {issue}`7`.
- \[mpm,macos\] Fix upgrade of `setuptools` in `macOS` and Python 3.3 Travis
  jobs.

## {gh}`2.0.0 (2016-12-04) <compare/v1.12.0...v2.0.0>`

- \[bar-plugin\] Rewrite BitBar plugin based on `mpm`. Closes {issue}`13`.
- \[bar-plugin\] Render errors with a monospaced font in BitBar plugin.
- \[mpm\] Add missing `CHANGES.rst` in `MANIFEST.in`.
- \[mpm\] Make wheels generated under Python 2 environnment available for
  Python 3 too.
- \[mpm\] Only show latest changes in the long description of the package
  instead of the full changelog.
- \[mpm\] Add link to full changelog in package's long description.
- \[mpm\] Bump trove classifiers status out of beta.
- \[mpm\] Fix package keywords.
- \[mpm\] Bump minimal `pycodestyle` requirement to 2.1.0.
- \[mpm\] Always check for package metadata in Travis CI jobs.
- \[mpm\] Add `upgrade_all_cli` field for each package manager in JSON output
  of `mpm outdated` command.

## {gh}`1.12.0 (2016-12-03) <compare/v1.11.0...v1.12.0>`

- \[mpm\] Rename `mpm update` command to `mpm upgrade`.
- \[mpm\] Allow restriction to only one package manager for each sub-command.
  Closes {issue}`12`.
- \[mpm\] Differentiate packages names and IDs. Closes {issue}`11`.
- \[mpm\] Sort list of outdated packages by lower-cased package names first.
- \[mpm\] Add `upgrade_cli` field for each outdated packages in JSON output.
- \[mpm,bar-plugin\] Allow user to choose rendering of `upgrade_cli` field to
  either one-liner, fragments or BitBar format. Closes {issue}`14`.
- \[mpm\] Include errors reported by each manager in JSON output of
  `mpm outdated` command.
- \[cask\] Fix parsing of multiple versions of `cask` installed packages.
- \[brew,cask\] Fix lexicographical sorting of `brew` and `cask` package
  versions.
- \[mpm\] Fix fall-back to iterative full upgrade command.
- \[mpm\] Fix computation of outdated packages statistics.

## {gh}`1.11.0 (2016-11-30) <compare/v1.10.0...v1.11.0>`

- \[mpm\] Allow rendering of output data into `json`.
- \[mpm\] Sort list of outdated packages by lower-cased package IDs.
- \[brew,cask\] Bump minimal requirement of `brew` to 1.0.0 and `cask` to
  1.1.0.
- \[cask\] Fix fetching of outdated `cask` packages.
- \[cask\] Fix upgrade of `cask` packages.

## {gh}`1.10.0 (2016-10-04) <compare/v1.9.0...v1.10.0>`

- \[mpm\] Add optionnal `version` property on package manager definitions.
- \[mpm\] Allow each package manager to set requirement on its own version.
- \[mas\] Let `mas` report its own version.
- \[mas\] Bump minimal requirement of `mas` to 1.3.1.
- \[mas\] Fetch currently installed version from `mas`. Closes {issue}`4`.
- \[mas\] Fix parsing of `mas` package versions after the 1.3.1 release.
- \[mpm\] Cache lazy properties to speed metadata computation.
- \[mpm\] Shows detailed state of package managers in CLI.

## {gh}`1.9.0 (2016-09-23) <compare/v1.8.0...v1.9.0>`

- \[mpm\] Fix `bumpversion` configuration to target `CHANGES.rst` instead of
  `README.rst`.
- \[mpm\] Render list of detected managers in a table.
- \[macos\] Use `conda` in Travis tests to install specific versions of Python
  across the range of macOS workers.
- \[macos\] Drop support for PyPy while we search a way to install it on macOS
  with Travis.
- \[mpm\] Let `mpm` auto-detect package manager definitions.
- \[mpm\] Show package manager IDs in `mpm managers` CLI output.
- \[mpm\] Rename `package_manager.7h.py` BitBar plugin to
  `meta_package_manager.7h.py`.
- \[mpm\] Give each package manager its own dedicated short string ID.
- \[mpm\] Keep a cache of instanciated package manager.
- \[mpm\] Add unittests around package manager definitions.
- \[mpm\] Do not display location of inactive managers, even if hard-coded.
- \[mpm\] Split-up CLI-producing methods and CLI running methods in
  `PackageManager` base class.
- \[mpm\] Add a new `update` CLI sub-command.
- \[mpm\] Add a new `sync` CLI sub-command.
- \[mpm\] Rename managers' `active` property to `available`.
- \[mpm\] Move all package manager definitions in a dedicated folder.
- \[mpm\] Add simple CLI unittests. Closes {issue}`2`.
- \[mpm\] Implement `outdated` CLI sub-command.
- \[mpm\] Allow selection of table rendering.
- \[cask\] Fix parsing of unversioned cask packages. Closes {pr}`6`.

## {gh}`1.8.0 (2016-08-22) <compare/v1.7.0...v1.8.0>`

- \[mpm\] Move the plugin to its own repository.
- \[mpm\] Rename `package-manager` project to `meta-package-manager`.
- \[mpm\] Add a `README.rst` file.
- \[mpm\] License under GPLv2+.
- \[mpm\] Add `.gitignore` config.
- \[mpm\] Add Python package skeleton. Closes {issue}`1`.
- \[mpm\] Split `CHANGES.rst` out of `README.rst`.
- \[mpm\] Add Travis CI configuration.
- \[mpm\] Use semver-like 3-components version number.
- \[bar-plugin\] Copy all BitBar plugin code to Python module.
- \[mpm\] Give each supported package manager its own module file.
- \[mpm\] Add minimal `mpm` meta CLI to list supported package managers.
- \[mpm\] Add default `bumpversion`, `isort`, `nosetests`, `coverage`, `pep8`
  and `pylint` default configuration.

## {gh}`1.7.0 (2016-08-16) <compare/v1.6.0...v1.7.0>`

- \[brew\] Fix issues with `$PATH` not having Homebrew/Macports.
- \[pip\] New workaround for full `pip` upgrade command.
- \[cask\] Workaround for Homebrew Cask full upgrade command.
- \[mpm\] Grammar fix when 0 packages need to be upgraded.

## {gh}`1.6.0 (2016-08-10) <compare/v1.5.0...v1.6.0>`

- \[pip\] Work around the lacks of full `pip` upgrade command.
- \[mpm\] Fix `UnicodeDecodeError` on parsing CLI output.

## {gh}`1.5.0 (2016-07-25) <compare/v1.4.0...v1.5.0>`

- \[mas\] Add support for `mas`.
- \[mpm\] Don't show all `stderr` as `err` (check return code for error state).

## {gh}`1.4.0 (2016-07-10) <compare/v1.3.0...v1.4.0>`

- \[mpm\] Don't attempt to parse empty lines.
- \[npm\] Check for linked `npm` packages.
- \[gem\] Support system or Homebrew Ruby Gems (with proper `sudo` setup).

## {gh}`1.3.0 (2016-07-09) <compare/v1.2.0...v1.3.0>`

- \[mpm\] Add changelog.
- \[mpm\] Add reference to package manager's issues.
- \[cask\] Force Cask update before evaluating available packages.
- \[mpm\] Add sample of command output as version parsing can be tricky.

## {gh}`1.2.0 (2016-07-08) <compare/v1.1.0...v1.2.0>`

- \[pip,npm,apm,gem\] Add support for both `pip2` and `pip3`, Node's `npm`,
  Atom's `apm`, Ruby's `gem`.
- \[cask\] Fixup `brew cask` checking.
- \[mpm\] Don't die on errors.

## {gh}`1.1.0 (2016-07-07) <compare/v1.0.0...v1.1.0>`

- \[pip\] Add support for Python's `pip`.

## {gh}`1.0.0 (2016-07-05) <commit/170ce9>`

- \[mpm\] Initial public release.
- \[brew,cask\] Add support for Homebrew and Cask.

```{todo}
Replace sub-title above with shorter `` {commit}`1.0.0 (2016-07-05) <170ce9>` ``
role once {issue}`sloria/sphinx-issues#116` is resolved.
```
