# Changelog

## [`7.2.0.dev0` (unreleased)](https://github.com/kdeldycke/meta-package-manager/compare/v7.1.0...main)

> [!WARNING]
> This version is **not released yet** and is under active development.

- [mpm] Fix benchmark data: merge the duplicate OpenBSD (`pkg-mgr`/`pkg-tools`), `gh-ext` and `pwsh-gallery` rows; add missing `pkcon`, `fink`, `sorcery` and `urpmi` rows; fix `winget`, `dnf`, `scoop` and `cask` competitor flags.
- [mpm] Config-defined managers gain multi-binary and privilege support: a per-operation `cli` key runs an operation through a sibling binary, `sudo = true` marks it privileged (honoring the new `default_sudo` definition field and the global `--sudo`/`--no-sudo` policy), and `version_cli` probes an alternate binary for tool suites exposing no version flag.
- [mpm] `mpm` is now a strict superset of `pacaptr`, `pacapt`, `sysget` and `whohas`: every package manager those tools support is now wrapped.
- [mpm] Extend the destructive install/remove test round-trip to the bundled configuration-defined managers; CI exercises it for real against `gh-ext`.
- [mpm] Manager definitions gain Brewfile export mappings: the new definition-only `brewfile_entry_type` and `brewfile_skip_warning` fields mirror the class attributes consumed by `mpm dump --brewfile`.
- [mpm] Loosen and tighten the definition schema: an `installed` query may now capture no version (for tools whose packages are unversioned), a `search` may omit the `{query}` placeholder to list the whole catalog and rely on client-side refiltering, and any unrecognized `{placeholder}` token in operation args is now rejected at load time.
- [mpm] Require click-extra `8.3` or newer.
- [mpm] Rename the `stats` configuration key to `summary`, matching the `--summary` option it was detached from; add `sudo`, `jobs` and `network` to the typed configuration schema; stop the schema from advertising a flat `500` default for `timeout`, which is resolved per operation.
- [mpm] Render the configuration reference, the CLI reference and the benchmark's manager-support table live at documentation build time, through click-extra's `click:config`, `click:tree` and `python:render` directives; drop `sphinx-click`.
- [mpm] Make the binaries catalog table searchable and sortable, with relative-age hints on release dates.
- [mpm] Exercise every subcommand's `--help` screen against the compiled binaries in the CLI test plan.
- [apt-cyg] Add apt-cyg (Cygwin) package manager with `installed`, `search`, `install`, `remove` and `sync` support on Windows/Cygwin; a bundled configuration-defined manager.
- [cargo] Convert from a Python class to a bundled configuration-defined manager. The optional description column of search results is no longer populated.
- [cave] Add cave (Exherbo's Paludis client) with `installed`, `install`, `upgrade`, `remove`, `sync` and `cleanup` support; a bundled configuration-defined manager.
- [chromebrew] Add Chromebrew (`crew`) package manager with `installed`, `search`, `install`, `upgrade`, `remove` and `sync` support on ChromeOS; a bundled configuration-defined manager.
- [cpan] Convert from a Python class to a bundled configuration-defined manager, with no functional change.
- [fink] Add Fink package manager with `installed`, `search`, `install`, `upgrade`, `remove`, `sync` and `cleanup` support on macOS; a bundled configuration-defined manager.
- [gh-ext] Report installed extensions by their `owner/repo` slug instead of the bare extension name, so the ids returned by `mpm installed` and `mpm backup` feed back into `install`, `remove`, `upgrade` and `restore`.
- [opkg] Convert from a Python class to a bundled configuration-defined manager. The optional description column of search results is no longer populated.
- [pkcon] Add PackageKit's console client (`pkcon`) with `installed`, `outdated`, `search`, `install`, `upgrade`, `remove` and `sync` support on Linux. Requires PackageKit `>=0.7.0`.
- [pkg-tools] Add OpenBSD's pkg tools (`pkg_add`/`pkg_info`/`pkg_delete`) with `installed`, `search`, `install`, `upgrade`, `remove` and `cleanup` support; a bundled configuration-defined manager.
- [pkgin] Add pkgin (NetBSD pkgsrc) package manager with `installed`, `outdated`, `search`, `install`, `upgrade`, `remove`, `sync` and `cleanup` support; a bundled configuration-defined manager.
- [slapt-get] Add slapt-get (Slackware) package manager with `installed`, `search`, `install`, `upgrade`, `remove`, `sync` and `cleanup` support; a bundled configuration-defined manager.
- [sorcery] Add Sorcery (Source Mage GNU/Linux) package manager with `installed`, `search`, `install`, `upgrade`, `remove`, `sync` and `cleanup` support; a bundled configuration-defined manager.
- [steamcmd] Convert from a Python class to a bundled configuration-defined manager, with no functional change.
- [sun-tools] Add Solaris' SVR4 package tools (`pkginfo`/`pkgrm`) with `installed` and `remove` support: SVR4 packages come from local media, so there is no repository to search, install from or upgrade against.
- [swupd] Add Clear Linux's swupd with `installed`, `search`, `install`, `upgrade --all`, `remove` and `cleanup` support, operating on bundles; a bundled configuration-defined manager.
- [tazpkg] Add TazPkg (SliTaz GNU/Linux) package manager with `installed`, `search`, `install`, `upgrade`, `remove`, `sync` and `cleanup` support.
- [tlmgr] Add TeX Live Manager (`tlmgr`) with `installed`, `outdated`, `search`, `install`, `upgrade`, `remove`, `sync` and `cleanup` support, cross-platform; a bundled configuration-defined manager. Requires TeX Live `>=2018`.
- [topgrade] Convert from a Python class to a bundled configuration-defined manager, with no functional change.
- [urpmi] Add urpmi (Mageia and the Mandriva lineage) with `installed`, `outdated`, `search`, `install`, `upgrade`, `remove`, `sync` and `cleanup` support; a bundled configuration-defined manager.
- [vscode] Convert from a Python class to a bundled configuration-defined manager, with no functional change.
- [vscodium] Convert from a Python class to a bundled configuration-defined manager, with no functional change.

## [`7.1.0` (2026-07-07)](https://github.com/kdeldycke/meta-package-manager/compare/v7.0.1...v7.1.0)

> [!NOTE]
> `7.1.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/7.1.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v7.1.0).

- **Breaking:** [mpm] Split the `[sbom]` extra into `[sbom-offline]` (CycloneDX and SPDX document rendering) and `[sbom-online]` (the `--network` vulnerability lookups). `pip install meta-package-manager[sbom]` no longer resolves: use `[sbom-offline]` for the previous behavior, adding `[sbom-online]` for vulnerability scanning.
- [mpm] Define brand-new package managers from the configuration file: a `[mpm.managers.<id>]` section declares a manager's platforms, CLI and version detection, and per-operation commands with `regex` or JSON parsers. Defined managers get `--<id>` / `--no-<id>` selectors and join the default set.
- [mpm] Manager definitions load only from a trusted local config file (owned by you, not world-writable, never a remote `--config` URL), and a command-redirecting override (`pre_cmds`, `cli_names`, `cli_search_path`) read from an untrusted source now warns: see the new {doc}`security` page.
- [mpm] Ship package managers as bundled configuration definitions: TOML files under `meta_package_manager/managers/`, built through the same schema as a user's `[mpm.managers.<id>]` section but loaded at startup like built-ins and exempt from the config-file trust gate.
- [gh-ext] Add GitHub CLI extensions (`gh extension`) manager with `installed`, `search`, `install`, `upgrade`, and `remove` support, cross-platform on Linux, macOS, and Windows; mpm's first bundled configuration-defined manager. Requires gh `>=2.0.0`.
- [soar] Add Soar (pkgforge) package manager with `installed`, `search`, `install`, `upgrade`, `remove`, `sync`, and `cleanup` support on Linux; a bundled configuration-defined manager. Requires soar `>=0.12.0`.
- [conda] Add Conda package manager with `installed`, `outdated`, `search`, `install`, `upgrade`, `remove`, and `cleanup` support, cross-platform on Linux, macOS, and Windows; requires conda `>=4.6.0`.
- [mpm] Add a global `--network / --no-network` flag (default off) that opts into network calls during a run.
- [mpm] `mpm --network sbom` queries [OSV.dev](https://osv.dev) for known vulnerabilities across OSV's indexed ecosystems (pip, npm, cargo, gem, composer): CycloneDX gains a `vulnerabilities` array, SPDX per-package `SECURITY` external references, and the end-of-run summary a vulnerability count.
- [mpm] OSV responses are cached on disk; network failures, a missing extra, or an unwritable cache degrade gracefully to an SBOM without vulnerability data.
- [mpm] Privilege escalation is now per-manager: system package managers still run state-changing operations through `sudo` by default, and a new global `--sudo` / `--no-sudo` flag or per-manager `[mpm.managers.<id>] sudo` config key overrides that either way. Resolves [#1295](https://github.com/kdeldycke/meta-package-manager/issues/1295) and [#33](https://github.com/kdeldycke/meta-package-manager/issues/33).
- [mpm] Escalating commands authenticate `sudo` once up front and run through `sudo -n`, so a password prompt no longer stalls the concurrent fan-out; off a terminal, managers needing root fail fast with a message pointing at `--sudo` instead of hanging.
- [yay] Honor `--cooldown` by overlaying a generated `init.lua` through a private `XDG_CONFIG_HOME`, holding back AUR upgrades and installs newer than the release-age floor while preserving the user's own yay config. Requires yay `13.0.0` for its Lua hooks.
- [mpm] The CLI gains a global `--export-config FORMAT` option that prints the fully-resolved configuration (config file, environment, and defaults merged) as `toml`, `yaml`, `json`, `json5`, `jsonc`, `hjson`, or `xml`, then exits.
- [mpm] Managers sharing a backend lock (`brew`/`cask`, `apt`/`apt-mint`/`deb-get`, the RPM and pacman families) now run serially within their family during state-changing commands; members resolving to an identical command run it once. Fixes spurious `cask` failures when syncing alongside `brew`.
- [mpm] A single Ctrl+C now aborts a concurrent command promptly: the first interrupt terminates in-flight package-manager subprocesses, so the thread pool drains and the run exits cleanly instead of hanging until a second Ctrl+C and a threading-shutdown traceback.
- [mpm] `--timeout` now also bounds the manager version-detection probes, not just the operation that follows, so a wedged binary cannot outlast the limit during startup detection.
- [bar-plugin] Cap each `mpm` call the plugin makes at 60 seconds via `--timeout`, so a wedged package manager fails the menubar refresh in about a minute instead of stalling it for several.
- [mpm] Raise the click-extra floor from `8.1.1` to `8.2.0`, the first release shipping the concurrency primitives, the `--export-config` option, and the compatibility-matrix machinery `mpm` relies on.
- [guix] Meta Package Manager is now [available in GNU Guix](https://packages.guix.gnu.org/packages/meta-package-manager/) upstream, installable with `guix install meta-package-manager`.
- [guix] Rename the reference package to `meta-package-manager`, fetch its source from the tagged git commit, build it with `setuptools.build_meta`, drop the now-optional SBOM and `more-itertools` inputs, and fix the `python-packageurl` input name so `guix install --load-path=packaging/guix` resolves.
- [nix] Drop the now-optional SBOM and `more-itertools` dependencies from the reference package definition.
- [pip] Only target a Python the user can actually install into: mpm's own bundled virtualenv and externally-managed interpreters (PEP 668) are skipped, so distro-managed packages no longer surface as bogus `outdated` pip upgrades. Supersedes the dependency-tree filter from [#1767](https://github.com/kdeldycke/meta-package-manager/issues/1767).
- [pip] Probe the Python interpreter version under the short read-only timeout instead of the long state-changing default.
- [mpm] The `--cooldown` help now shows `[default: (disabled)]` instead of the bare `[default: ""]`, so the unset state reads as a word rather than an empty string.
- [dnf] `upgrade` and `upgrade --all` now pass `--assumeyes`, as the other dnf operations already did, so upgrades no longer hang on an interactive confirmation prompt.
- [eopkg] `upgrade --all` now passes `--yes-all`, matching the single-package upgrade, so it no longer hangs on an interactive confirmation prompt.
- [fwupd] Fix version-pinned installs: the device ID and release version were joined into a single CLI argument that `fwupdmgr` could not parse.
- [npm] `install` no longer passes `--no-fund` and `--no-audit` twice.
- [mpm] The installation page now documents which Python and click-extra versions each `mpm` release accepts, in tables regenerated from the release tags and guarded by a drift test.
- [mpm] Catalog every released standalone binary on a new documentation page, linking each platform build to its download and public VirusTotal analysis, with a detection-rate trend chart.
- [mpm] Add a hermetic test replaying each manager's documented CLI samples through its own parsers and command builders, covering `installed`, `outdated`, `--version`, and the mutation commands; corrected the stale samples flagged across a dozen managers. Toward [#1023](https://github.com/kdeldycke/meta-package-manager/issues/1023).

## [`7.0.1` (2026-06-27)](https://github.com/kdeldycke/meta-package-manager/compare/v7.0.0...v7.0.1)

> [!NOTE]
> `7.0.1` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/7.0.1/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v7.0.1).

- [mpm] Fix `ParameterSource` import from older Click dependency.

## [`7.0.0` (2026-06-26)](https://github.com/kdeldycke/meta-package-manager/compare/v6.6.0...v7.0.0)

> [!NOTE]
> `7.0.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/7.0.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v7.0.0).

- **Breaking:** [mpm] Rename the `--allow-no-cooldown` flag to the `--require-cooldown-support`/`--allow-unsupported-managers` pair, and its `allow_no_cooldown` config to `require_cooldown_support` (default `true`).
- **Breaking:** [mpm] The `sort_by` configuration option is now a list of fields, matching the repeatable `--sort-by`. Wrap an existing scalar value in brackets: `sort_by = "package_id"` becomes `sort_by = ["package_id"]`.
- [pnpm] Add the pnpm package manager (`installed`, `outdated`, `search`, `install`, `upgrade`, `remove`, `cleanup`), enforcing `--cooldown` via pnpm's native `minimumReleaseAge` gate.
- [mpm] Filter the package listing by a query: `installed` and `outdated` take an optional `QUERY` argument and `dump`/`backup`/`sbom` a `--query` option, fuzzy by default with `--exact`/`--fuzzy` to control it.
- [mpm] `--sort-by`/`-s` is now repeatable, ordering result tables by several fields in priority order (like `--sort-by package_id --sort-by manager_id`).
- [mpm] Run managers in parallel via a new `--jobs`/`-j` option (default: CPU count minus one), covering the read-only queries, the maintenance commands, the inventory exporters, and the state changers; `DEBUG` verbosity forces sequential runs. Closes [#529](https://github.com/kdeldycke/meta-package-manager/issues/529).
- [mpm] Show a progress spinner with elapsed time on `<stderr>` while manager CLI calls run, toggled with click-extra's `--progress`/`--no-progress`.
- [mpm] `install`, `remove`, `upgrade`, `restore`, `sync`, and `cleanup` now print a per-attempt `✓`/`✗` trail and a finisher on an interactive terminal: per-package for the package commands, per-manager for `sync`/`cleanup`/`upgrade --all`.
- [mpm] The standalone binary now reads configuration in all six formats (`toml`, `yaml`, `json5`, `jsonc`, `hjson`, `xml`), matching the source distribution.
- [mpm] Lower the default verbosity from `INFO` to `WARNING`, leaving only the `✓`/`✗` trail, finishers, and genuine warnings on screen; per-operation narration moves to `INFO` and raw technical detail to `DEBUG`.
- [mpm] `--timeout` now defaults per-operation (120s for read-only queries, 500s for state-changing operations) instead of a flat 500s; an explicit `--timeout` still overrides.
- [mpm] `install`, `remove`, `upgrade <packages>`, and `restore` now exit non-zero when a target fails or no manager can fulfill the request, instead of always reporting `0`.
- [mpm] Fix `install`/`remove`/`upgrade` dropping all but one target when the same package is given with several explicit managers; `install` now acts on every requested package instead of stopping at the first success.
- [mpm] Fix `install`, `remove`, and `upgrade` reporting success when a manager's CLI fails with a non-zero exit code but empty error output, like steamcmd's anonymous-login failure on Windows.
- [eopkg] Fix `installed`, `outdated`, and `search` returning no packages.
- [mpm] Compare a leading version epoch (`1:2.0`, `1!2.0`) as a dominant component, so epoch bumps order correctly across Debian, RPM, pacman, and PEP 440 schemes.
- [mpm] Resolve `pkg:apk` purls to the `apk` manager and `pkg:npm` purls to `pnpm`; both were missing from the purl-to-manager map.

## [`6.6.0` (2026-06-17)](https://github.com/kdeldycke/meta-package-manager/compare/v6.5.1...v6.6.0)

> [!NOTE]
> `6.6.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/6.6.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v6.6.0).

- **Breaking:** [mpm] Rename the global `--stats / --no-stats` flag to `--summary / --no-summary`. Scripts passing the old flag must update.
- **Breaking:** [mpm] Move `cyclonedx-python-lib` and `spdx-tools` into a new `[sbom]` extra: `mpm sbom` now requires `pip install meta-package-manager[sbom]`. `packageurl-python` stays in the runtime install. The standalone binary distribution keeps shipping SBOM support: `[tool.repomatic] nuitka.extras = ["sbom"]` syncs the extra into the build venv and `[tool.nuitka] include-package = ["cyclonedx", "spdx_tools"]` forces Nuitka to bundle the `try/except`-guarded imports.
- [asdf] Add [asdf](https://asdf-vm.com) package manager (`installed`, `outdated`, `search`, `install`, `upgrade`, `upgrade_all`, `remove`, `sync`) on Linux and macOS; requires `asdf` `>=0.16.0`.
- [mise] Add [mise](https://mise.jdx.dev) package manager (`installed`, `outdated`, `search`, `install`, `upgrade`, `upgrade_all`, `remove`, `sync`, `cleanup`), cross-platform; requires `mise` `>=2025.5.10`.
- [mpm] Add the `--man` (roff man page) and `--accessible` (no ANSI or Unicode, for screen readers) global options from `click-extra`, and attach an `mpm-manpages.tar.gz` asset to each release.
- [mpm] Add a `--cooldown DURATION` option and `[mpm] cooldown` config to refuse installing or upgrading package versions newer than a given release age, as a supply-chain mitigation; unsupported managers are skipped unless `--allow-no-cooldown`.
- [brew] Adapt to Homebrew `6.0.0`: pass `--yes` to `brew upgrade` to suppress the new interactive prompt, and trust tap-qualified installs before installing to avoid `tap trust is required` aborts. Bumps minimum `brew` from `2.7.0` to `6.0.0`.
- [zerobrew] Add `upgrade` and `upgrade_all` support via `zb upgrade`, and bump minimum `zb` from `0.2.0` to `0.3.0`.
- [mpm] Make `mpm sbom` maximalist by default, collecting rich per-package metadata (license, supplier, homepage, checksums, dependency graph) into SPDX and CycloneDX exports, with `--minimal` for the bare inventory.
- [mpm] Attach canonical SPDX URLs to each identifier inside compound license expressions in CycloneDX 1.7 output (`licenses[].expressionDetails[]`).
- [mpm] Reduce default-verbosity noise on operational subcommands: captured stderr and implicit-selection `Skip` messages drop to DEBUG, with a one-line error summary at the end of any subcommand whose CLIs accumulated errors.
- [mpm] Fix `pkg:cpan/…`, `pkg:guix/…`, and `pkg:nix/…` pURL specifiers raising `Unrecognized pURL type` even though those managers are implemented.

## [`6.5.1` (2026-05-28)](https://github.com/kdeldycke/meta-package-manager/compare/v6.5.0...v6.5.1)

> [!NOTE]
> `6.5.1` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/6.5.1/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v6.5.1).

- [mpm] Define `mpm`'s own `OK_GLYPH` (`✓`) and `KO_GLYPH` (`✘`) constants in `meta_package_manager.output` instead of importing them from `click-extra`.

## [`6.5.0` (2026-05-25)](https://github.com/kdeldycke/meta-package-manager/compare/v6.4.3...v6.5.0)

> [!NOTE]
> `6.5.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/6.5.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v6.5.0).

- [pwsh-gallery] Add PowerShell Gallery package manager with `installed`, `outdated`, `search`, `install`, `upgrade`, and `remove` support. Drives `Microsoft.PowerShell.PSResourceGet` (PowerShell 7.4+), installs to `-Scope CurrentUser`, cross-platform on Linux, macOS, and Windows. Closes [#1760](https://github.com/kdeldycke/meta-package-manager/issues/1760).
- [topgrade] Add `topgrade` itself as a supported manager; only `upgrade --all` is implemented (`mpm upgrade --topgrade` runs `topgrade --yes`). Requires `topgrade` >= `17.0.0`. Beware running a manager twice if both are selected.
- [mpm] Add `[mpm.managers.<id>]` config sections for per-manager attribute overrides, taking precedence over global `[mpm]` settings and `--<flag>` values. Closes [#945](https://github.com/kdeldycke/meta-package-manager/issues/945).
- [mpm] Print an upstream contribution invitation on `<stderr>` with a pre-filled GitHub issue URL when an override targets a detection-related field. Silence via `--no-suggest-contribs`, `MPM_SUGGEST_CONTRIBS=false`, or `[mpm] suggest_contribs = false`.
- [mpm] Add `mpm config-template [manager-ids...]` subcommand that prints every overridable manager attribute as a ready-to-paste `[mpm.managers.<id>]` TOML block.
- [mpm] Add `mpm dump` to export the installed-package inventory as TOML (`--toml`) or a Brewfile (`--brewfile`); `mpm backup`, `mpm lock`, `mpm freeze`, and `mpm snapshot` are aliases.
- [bar-plugin] Swap default and alternate actions on package-upgrade entries: a regular click now opens a visible terminal, and holding `Option` runs the upgrade silently. Reverses the `3.3.0` behavior.
- [mpm] Remove automated publishing of the Chocolatey package; install instructions in `docs/install.md` now point only at the local build path.
- [mas] Bump minimum required `mas` version from `1.8.7` to `7.0.0`, switch `installed`, `outdated`, and `search` to parse `--json` output, update `homepage_url` to `https://github.com/mas-cli/mas`, and drop the explicit `sudo` wrapper around `mas uninstall`.
- [mpm] Fix several Windows subprocess issues: hidden console windows, winget `CTRL_C_EVENT` handling, grandchild-process cleanup on timeout, missing-executable detection, and interactive-prompt hangs.
- [yarn] Fix `search` to parse NDJSON output line by line, collecting only `inspect`-type entries, since newer Yarn emits multiple JSON objects with a trailing status line.
- [mpm] Fix Nuitka onefile builds by configuring the binary through the standard `[tool.nuitka]` section, bundling `click_extra`'s `themes.toml`, and carrying product metadata and native per-platform icons.
- [xbps] Add Void Linux build-from-source installation instructions to `docs/install.md`.

## [`6.4.3` (2026-05-11)](https://github.com/kdeldycke/meta-package-manager/compare/v6.4.2...v6.4.3)

> [!NOTE]
> `6.4.3` is available on [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v6.4.3).

> [!WARNING]
> `6.4.3` is **not available** on 🐍 PyPI.

- [mpm] Re-release to fix PyPI upload issues.

## [`6.4.2` (2026-05-08)](https://github.com/kdeldycke/meta-package-manager/compare/v6.4.1...v6.4.2)

> [!NOTE]
> `6.4.2` is available on [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v6.4.2).

> [!WARNING]
> `6.4.2` is **not available** on 🐍 PyPI.

- [mpm] Compile `version_regexes` with `re.MULTILINE` only, dropping `re.VERBOSE`, so patterns with unescaped whitespace match again; fixes version detection for `guix`, `nix`, and `stew`.

## [`6.4.1` (2026-05-04)](https://github.com/kdeldycke/meta-package-manager/compare/v6.4.0...v6.4.1)

> [!NOTE]
> `6.4.1` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/6.4.1/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v6.4.1).

- [guix] Drop the `>=1.0.0` version requirement and add a hex-hash regex variant, so `guix pull` installs and dev wrappers reporting a git commit hash register as available.
- [mpm] Add `PackageManager.unavailable_reason` and surface it in the pool's "Skip" log line, spelling out why a manager was dropped from selection.
- [mpm] Move `--cov` and `--cov-report=term` out of `pyproject.toml` `addopts` into the CI workflow, dropping `pytest-cov` as an unconditional test dependency.
- [mpm] Move `--numprocesses=auto`, `--dist=loadgroup`, and `--maxschedchunk=1` out of `pyproject.toml` `addopts` into the CI workflow, dropping `pytest-xdist` as an unconditional test dependency.
- [zypper] Loosen the `xmltodict` floor from `>=1` to `>=0.12`.
- [mpm] Drop the `more-itertools` dependency, replacing the single `peekable` use with stdlib `next(iterator, None)`.
- [choco] Move Chocolatey package files into `packaging/choco/meta-package-manager/` so the directory name matches the nuspec basename, fixing the release job.
- [mpm] Add `choco-source`, `nix-source`, and `guix-source` jobs to `tests-install.yaml` that build and install from the in-repo packaging specs.
- [mpm] Render the `chocolatey`, `guix`, and `nix` release-PR bodies through `repomatic pr-body`, adding the standard workflow-metadata block and attribution footer.

## [`6.4.0` (2026-04-27)](https://github.com/kdeldycke/meta-package-manager/compare/v6.3.0...v6.4.0)

> [!NOTE]
> `6.4.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/6.4.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v6.4.0).

- [apk] Add Alpine Linux's `apk` package manager with `installed`, `outdated`, `search`, `install`, `upgrade`, `remove`, `sync`, and `cleanup` support.
- [guix] Add GNU Guix package manager with `installed`, `outdated`, `search`, `install`, `upgrade`, `remove`, `sync`, and `cleanup` support.
- [macports] Add MacPorts package manager with `installed`, `outdated`, `search`, `install`, `upgrade`, `remove`, `sync`, and `cleanup` support.
- [ports] Add FreeBSD ports tree manager with `installed`, `outdated`, `install`, `upgrade`, `upgrade_all`, `remove`, `sync`, and `cleanup` support. Drives `make`-based source builds out of `/usr/ports`, delegates registry queries to `pkg`, and uses `git` for tree updates.
- [sfsu] Add sfsu (Scoop alternative) package manager with `installed`, `outdated`, `search`, `install`, `upgrade`, `remove`, `sync`, and `cleanup` support. Mutating operations delegate to Scoop.
- [xbps] Add XBPS (Void Linux) package manager with `installed`, `outdated`, `search`, `install`, `upgrade`, `remove`, `sync`, and `cleanup` support.
- [apm,apt,choco,composer,emerge,flatpak,opkg,sdkman,snap,zypper] Add `remove` operation. Closes [#1775](https://github.com/kdeldycke/meta-package-manager/issues/1775).
- [composer] Fix `install` operation: use `composer global require` instead of `composer global install`.
- [apm,npm,pip] Add `cleanup` operation.
- [gem,winget] Add `sync` operation.
- [mpm] Add `Delegate` descriptor to `capabilities.py` for declarative cross-manager method delegation.
- [mpm] Add Python version and platform to `--version` output.
- [mpm] Add typed `config_schema` to the CLI group for configuration file validation.
- [mpm] Document `pyproject.toml` auto-discovery for per-project `[tool.mpm]` configuration.
- [mpm] Extend `--table-format` structured output to TOML, YAML, XML, JSON5, JSONC, and HJSON for all subcommands that produce machine-readable data (`managers`, `installed`, `outdated`, `search`, `locate`).
- [mpm] Change JSON output indentation from 4 to 2 spaces and stop sorting keys, aligning with click-extra defaults.
- [mpm] Rename `--output-format` / `-o` back to `--table-format`, aligning with the upstream click-extra default.
- [mpm] Make Chocolatey release job idempotent: check if version already exists on Chocolatey before pushing, and open a PR to update the nuspec after a successful publish.
- [mpm] Add Guix and Nix package definitions with automated update jobs on release; reorganize `packaging/` directory into `packaging/choco/`, `packaging/guix/`, and `packaging/nix/` subdirectories.
- [pip] Filter mpm's own dependency tree from `outdated` results to fix false positives in Homebrew-installed environments. Closes [#1767](https://github.com/kdeldycke/meta-package-manager/issues/1767).
- [scoop] Fix CLI invocation in `outdated` operation.
- [winget] Fix `search` crash when no results are returned.
- [zypper] Skip install and remove tests on Linux CI runners: the RPM database at `/var/lib/rpm` is inaccessible on Ubuntu-based runners.

## [`6.3.0` (2026-04-09)](https://github.com/kdeldycke/meta-package-manager/compare/v6.2.1...v6.3.0)

> [!NOTE]
> `6.3.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/6.3.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v6.3.0).

- [cpan] Add CPAN package manager for Perl modules with `installed`, `outdated`, `install`, and `upgrade` support. Closes [#602](https://github.com/kdeldycke/meta-package-manager/issues/602).
- [deb-get] Add deb-get package manager with `installed`, `outdated`, `search`, `install`, `upgrade`, `remove`, `sync`, and `cleanup` support. Closes [#1609](https://github.com/kdeldycke/meta-package-manager/issues/1609).
- [nix] Add Nix package manager with `installed`, `outdated`, `search`, `install`, `upgrade`, `remove`, `sync`, and `cleanup` support.
- [pacstall] Add Pacstall package manager with `installed`, `outdated`, `search`, `install`, `upgrade`, `remove`, and `sync` support. Closes [#1610](https://github.com/kdeldycke/meta-package-manager/issues/1610).
- [sdkman] Add SDKMAN! package manager with `installed`, `outdated`, `install`, `upgrade`, `sync`, and `cleanup` support. Closes [#729](https://github.com/kdeldycke/meta-package-manager/issues/729).
- [stew] Add Stew package manager for installing pre-compiled binaries from GitHub Releases. Closes [#1680](https://github.com/kdeldycke/meta-package-manager/issues/1680).
- [zerobrew] Add ZeroBrew manager with `installed`, `outdated`, `install`, and `remove` support. Closes [#1681](https://github.com/kdeldycke/meta-package-manager/issues/1681).
- [uvx] Implement `outdated` operation. Bump minimal requirement to `0.10.10`. Closes [#1704](https://github.com/kdeldycke/meta-package-manager/pull/1704).
- [yarn] Split into Yarn Classic and Yarn Berry managers. Restrict Classic to `<2.0.0`. Closes [#1548](https://github.com/kdeldycke/meta-package-manager/issues/1548).
- [yarn-berry] Add Yarn Berry (2.x+) manager with `search` and `cleanup` support.
- [winget] Switch `installed` and `outdated` to `winget list --details` structured output; filter to `Origin Source: winget` packages only, excluding sideloaded and portable entries. Bump minimum required version to `>=1.28.190`.
- [pip] Only report top-level packages as outdated, skipping transitive dependencies. Closes [#1214](https://github.com/kdeldycke/meta-package-manager/issues/1214).
- [mpm] Support version range specifiers (e.g. `>=1.20.0,<2.0.0`) in manager `requirement` field. Refs [#1548](https://github.com/kdeldycke/meta-package-manager/issues/1548).
- [mpm] Add `must_succeed` parameter to `run_cli` for structured-output calls, preventing silent data loss on CLI failures. Refs [#1703](https://github.com/kdeldycke/meta-package-manager/issues/1703).
- [mpm] Add Chocolatey as a supported Windows installation method; automate package publishing on release.
- [mpm] Overhaul version tokenization: preserve original separators and case, keep hex hashes as single tokens, normalize pre-release aliases (`alpha`/`a`, `beta`/`b`, `c`/`rc`), and recognize `post`/`patch` as post-release tags.
- [mpm] Fix version comparison accuracy: integer tokens now rank above string tokens (e.g., `3.12.0 > 3.12.0a4`), trailing `.0` segments are treated as padding, the cosmetic `v` prefix is stripped, and false-positive outdated entries where parsed versions compare equal are filtered.
- [mpm] Snap version diff highlighting to separator boundaries so the full diverging token and its preceding separator are colored.
- [mpm] Detect Windows App Execution Aliases (reparse points) when resolving CLI paths, fixing detection of `winget` and similar tools installed via the Microsoft Store.
- [gem] Remove `--user-install` flag from `install`, `upgrade`, and `update` commands so all operations target the same gem scope as `list` and `outdated`. Closes [#389](https://github.com/kdeldycke/meta-package-manager/issues/389).
- [pip] Remove `--user` flag from `upgrade` command so upgrades target the same scope as `list` and `outdated`.
- [pip] Prepend the current Python executable to the list of candidates when searching for pip binaries, so the active environment is always checked first.
- [mpm] Cache installed package IDs before the spec loop in `upgrade` and `remove` commands, avoiding redundant CLI calls per package specifier.
- [mpm] Reduce CI matrix on pull requests: skip release builds, experimental Python versions, redundant architecture variants, and install tests. Declare `windows-11-arm` exclusion in `[tool.repomatic.test-matrix]` config instead of hardcoding it.

## [`6.2.1` (2026-03-26)](https://github.com/kdeldycke/meta-package-manager/compare/v6.2.0...v6.2.1)

> [!NOTE]
> `6.2.1` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/6.2.1/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v6.2.1).

- [brew,cask] Remove `--quiet` from `outdated` command where it conflicts with `--json`. Closes [#1703](https://github.com/kdeldycke/meta-package-manager/issues/1703).
- [npm] Fix crash on `installed` when no global packages are present. Closes [#1603](https://github.com/kdeldycke/meta-package-manager/issues/1603).
- [mpm] Fix `--no-color` having no effect on CSV output. Closes [#1004](https://github.com/kdeldycke/meta-package-manager/issues/1004).
- [mpm] Fix version reported by compiled (Nuitka) binaries. Closes [#1145](https://github.com/kdeldycke/meta-package-manager/issues/1145).

## [`6.2.0` (2026-03-25)](https://github.com/kdeldycke/meta-package-manager/compare/v6.1.1...v6.2.0)

> [!NOTE]
> `6.2.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/6.2.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v6.2.0).

- [mpm] Upgrade from reusable workflows to `repomatic`.
- [mpm] Inline `replace_content` utility from `click-extra` which was removed in `7.6.2`.
- [mpm] Simplify `uvx` invocation from `uvx --from meta-package-manager -- mpm` to `uvx meta-package-manager`.
- [brew,cask] Add `--quiet` option to all `brew` invocations to reduce log verbosity.
- [composer] Add `--no-ansi` option to all `composer` invocations.
- [composer] Fix search regex to strip whitespace-only descriptions.
- [dnf,dnf5,yum] Add `--quiet` option to all invocations to reduce log verbosity.
- [emerge] Add `--quiet`, `--color n` and `--nospinner` to `pre_args`. Refactor inline flags.
- [pacaur,pacman,paru,yay] Add `--color never` option to all invocations.
- [pkg] Add `--quiet` option to all `pkg` invocations to reduce log verbosity.
- [yarn] Add `--silent` option to all `yarn` invocations to suppress console logs.
- [mpm] Pre-compile regexes at class level across all managers.
- [mpm] Set CycloneDX SBOM lifecycle phase to `operations`.

## [`6.1.1` (2026-02-06)](https://github.com/kdeldycke/meta-package-manager/compare/v6.1.0...v6.1.1)

> [!NOTE]
> `6.1.1` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/6.1.1/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v6.1.1).

- [choco] Add `--retry-count=3` option to all `choco` invocations.
- [mpm] Upgrade to `extra-platforms` 8.0.0. Remove usage of deprecated functions.
- [mpm] Remove direct dependency on `tabulate`.

## [`6.1.0` (2026-01-18)](https://github.com/kdeldycke/meta-package-manager/compare/v6.0.2...v6.1.0)

> [!NOTE]
> `6.1.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/6.1.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v6.1.0).

- [uvx] Add `uvx` support for managing isolated Python tools via `uv tool`. Closes [#1656](https://github.com/kdeldycke/meta-package-manager/issues/1656), [#1657](https://github.com/kdeldycke/meta-package-manager/pull/1657).

## [`6.0.2` (2026-01-09)](https://github.com/kdeldycke/meta-package-manager/compare/v6.0.1...v6.0.2)

> [!NOTE]
> `6.0.2` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/6.0.2/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v6.0.2).

- [uv] Workaround `uv` parsing issues with package specifiers by not quoting them. Closes [#1653](https://github.com/kdeldycke/meta-package-manager/issues/1653).

## [`6.0.1` (2026-01-02)](https://github.com/kdeldycke/meta-package-manager/compare/v6.0.0...v6.0.1)

> [!NOTE]
> `6.0.1` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/6.0.1/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v6.0.1).

- [mpm] Move auto-lock time from 8:43 to 4:43.
- [mpm] Set cooldown period via the `pyproject.toml`.
- [mpm] Add Download link to project metadata.
- [mpm] Include license file in package.
- [mpm] Replace deprecated `codecov/test-results-action` by `codecov/codecov-action`.
- [mpm] Remove utilization workaround for `macos-15-intel`.

## [`6.0.0` (2025-12-08)](https://github.com/kdeldycke/meta-package-manager/compare/v5.21.0...v6.0.0)

> [!NOTE]
> `6.0.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/6.0.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v6.0.0).

- [mpm] Add `--no-config` option inherited from Click Extra.
- [mpm] Replace Click Extra's default `--table-format` option by our `--output-format` option, which allows sorted table rendering and JSON output.
- [scoop] Fix parsing of `scoop` version to support raw Git output.
- [gem] Remove hard-coded `gem` CLI search path.
- [mpm] Remap pURL types to managers. Closes [#1460](https://github.com/kdeldycke/meta-package-manager/issues/1460).
- [mpm] Allow multiple regular expressions to be used for version matching.
- [mpm] Remove maximum capped version of all dependencies (relax all `~=` specifiers to `>=`). This gives more freedom to downstream and upstream packagers. Document each minimal version choice.
- [mpm] Add cooldown period for dependabot and `uv.lock` updates.
- [mpm] Merge all label syncing jobs into a single one.
- [mpm] Add `yaml`, `json5`, `jsonc`, `hjson` and `xml` extra dependencies to support respective configuration file formats.
- [mpm] Change the `test`, `typing` and `docs` extra dependency groups into development dependency groups.
- [mpm] Add official support of Python 3.14.
- [mpm] Re-introduce Python 3.10 support.
- [mpm] Run tests on Python `3.10`, `3.14`, `3.15`, `3.14t` and `3.15t`.
- [mpm] Skip tests on intermediate Python versions (`3.11`, `3.12` and `3.13`) to reduce CI load.
- [mpm] Produce `mpm-windows-arm64.exe` Windows binary for `arm64` architecture.
- [mpm] Replace `ubuntu-24.04` by `ubuntu-slim`, `macos-15` by `macos-26`, and `macos-13` by `macos-15-intel` in workflow jobs.
- [mpm] Unlock a CPU core stuck at 100% utilization on `macos-15-intel`.
- [mpm] Use `astral-sh/setup-uv` action to install `uv` instead of manually installing it with `pip`.
- [mpm] Move all typing-related imports behind a hard-coded `TYPE_CHECKING` guard to avoid runtime imports.

## [`5.21.0` (2025-05-29)](https://github.com/kdeldycke/meta-package-manager/compare/v5.20.0...v5.21.0)

> [!NOTE]
> `5.21.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.21.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.21.0).

- [mpm] Drop support for Python 3.10.
- [mpm] Fix parsing of package specifiers with multiple version separators.
- [npm] Fix retrieval of installed packages.
- [fwupd] Remove `--offline` parameter which has been silently disabled and has now been remove in v2.0.0 of `fwupd`. Refs [#1511](https://github.com/kdeldycke/meta-package-manager/pull/1511).
- [bar-plugin] Bump minimal Python version to 3.9 to aligns it with macOS default.
- [bar-plugin] Check minimal version of SwiftBar is 2.1.2.
- [bar-plugin] Reduce size of error messages from 12 to 10.
- [mpm] Remove reference to `python3` command in documentation to reduce confusion.
- [mpm] Build `arm64` binary for Linux.
- [mpm] Try to build `arm64` binary for Windows but mark it as unstable.
- [mpm] Use post-build binary test plans to check CLI behavior.
- [mpm] Run tests on `windows-2025` instead of `windows-2022`.
- [mpm] Reactivates concurrency limits on tests.
- [mpm] Uploads codecov test results.

## [`5.20.0` (2024-11-25)](https://github.com/kdeldycke/meta-package-manager/compare/v5.19.0...v5.20.0)

> [!NOTE]
> `5.20.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.20.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.20.0).

- [eopkg] Add support for new `eopkg` manager. Closes [#1093](https://github.com/kdeldycke/meta-package-manager/issues/1093).
- [fwupd] Add support for new `fwupd` manager. Closes [#1289](https://github.com/kdeldycke/meta-package-manager/issues/1289).
- [dnf5] Add support for new `dnf5` manager. Refs [#1423](https://github.com/kdeldycke/meta-package-manager/pull/1423).
- [mpm] Hide `--manager` and `--exclude` options from help output and silence deprecation warnings. Closes [#1358](https://github.com/kdeldycke/meta-package-manager/issues/1358).
- [mpm] Add detailed documentation on manager selection with configuration file.
- [mpm] Fix mixing of manager selector lists and flags.

## [`5.19.0` (2024-11-14)](https://github.com/kdeldycke/meta-package-manager/compare/v5.18.0...v5.19.0)

> [!NOTE]
> `5.19.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.19.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.19.0).

- [vscodium] Add support for VSCodium plugins.
- [dnf,mas,vscode,yum] Implement `remove` operation.
- [dnf,yum] Use query template instead of regex parsing to retrieve package data.
- [flatpak] Fix parsing of descriptions with spaces.
- [uv] Implement `outdated` and `cleanup` operation.
- [uv] Bump minimal requirement to `0.5.0`.
- [uv] Always invoke `uv` with `--no-progress` parameter.
- [mas] Bump minimal requirement to `1.8.7`.
- [mas] Reactivate `mas` tests.
- [mpm] Add official support for Python 3.13.
- [mpm] Drop support for Python 3.9.
- [mpm] Replace local platform utilities by `extra-platforms` dependency.
- [mpm] Run tests on Python 3.14-dev.
- [mpm] Run tests and actions on `ubuntu-24.04` instead of `ubuntu-22.04`.
- [mpm] Run tests on `macos-15` instead of `macos-14`.
- [mpm] Add a Sankey diagram of all supported package managers.

## [`5.18.0` (2024-08-02)](https://github.com/kdeldycke/meta-package-manager/compare/v5.17.0...v5.18.0)

> [!NOTE]
> `5.18.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.18.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.18.0).

- [mpm] Add new command to export installed packages to a SBOM file in SPDX or CycloneDX standard. Closes [#936](https://github.com/kdeldycke/meta-package-manager/issues/936).
- [mpm] Add new dependencies on `spdx-tools` and `cyclonedex-python-lib`.
- [mpm] Update list of recognized pURL scheme types.
- [apt] Add architecture in package metadata.

## [`5.17.0` (2024-07-08)](https://github.com/kdeldycke/meta-package-manager/compare/v5.16.0...v5.17.0)

> [!NOTE]
> `5.17.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.17.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.17.0).

- [uv] Add support for `uv` package manager for Python.
- [mpm] Add `--no-<manager-id>` negative selection flags for each single manager. Closes [#882](https://github.com/kdeldycke/meta-package-manager/issues/882).
- [mpm] Deprecate `-m`/`--manager` and `-e`/`--exclude` options in favor of single `--<manager-id>`/`--no-<manager-id>` selectors.
- [bar-plugin] Identify `uv`-based virtual envs to run `mpm` executable.
- [mpm] Stop CLI execution if manager selection parameters ends up with no managers being retained.
- [mpm] Switch from Poetry to `uv`.
- [mpm] Drop support for Python 3.8.
- [mpm] Add dependency on `more-itertools`.
- [mpm] Add metadata and icon to binaries produced by Nuitka.
- [mpm] Mark Python 3.13-dev tests as stable.
- [bar-plugin] Reactivate login shells invocation tests.
- [bar-plugin] Skip rendering tests on GitHub.
- [mpm] Remove `sys.path` cleaning hack in `__main__` invocation.
- [mpm] Reactivate config file test for `restore` subcommand.

## [`5.16.0` (2024-05-24)](https://github.com/kdeldycke/meta-package-manager/compare/v5.15.0...v5.16.0)

> [!NOTE]
> `5.16.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.16.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.16.0).

- [winget] Add support for WinGet on Windows. Closes [#500](https://github.com/kdeldycke/meta-package-manager/issues/500) and [#1241](https://github.com/kdeldycke/meta-package-manager/issues/1241).
- [scoop] Add `mpm` installation instructions with `scoop`.
- [bar-plugin] Dynamiccaly search for Python, virtual envs and `mpm` executable instead of relying on hard-coded `PATH` environment variable.
- [bar-plugin] Replace `--check-mpm` parameter by `--search-mpm` with complete results reporting.
- [mpm] Slim down package by moving unit tests out of the main package.
- [mpm] Split `dev` dependency groups into optional `test`, `typing` and `docs` groups.
- [mpm] Remove direct dependency on `click` and `mypy`.
- [mpm] Make `typing-extensions` dependency optional.

## [`5.15.0` (2024-02-25)](https://github.com/kdeldycke/meta-package-manager/compare/v5.14.2...v5.15.0)

> [!NOTE]
> `5.15.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.15.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.15.0).

- [pkg] Add support for `pkg` on FreeBSD.
- [choco] Bump minimal `choco` requirement to `2.0.0`.
- [bar-plugin] Keep original indention of Python traceback.
- [mpm] Build `arm64` binaries on `macos-14`.
- [mpm] Run tests on `macos-14` instead of `macos-13`.
- [mpm] Run tests on Python 3.13-dev branch.
- [mas] Deactivate integration tests for `mas` on macOS, which always timeout.
- [mpm] Reintroduce coloring of version. Refs [#1152](https://github.com/kdeldycke/meta-package-manager/pull/1152).
- [mpm] Use external workflow to manage issues and PRs content-based labelling.

## [`5.14.2` (2024-01-17)](https://github.com/kdeldycke/meta-package-manager/compare/v5.14.1...v5.14.2)

> [!NOTE]
> `5.14.2` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.14.2/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.14.2).

- [mpm] Fix installation from `pipx`. Closes [#1154](https://github.com/kdeldycke/meta-package-manager/issues/1154).

## [`5.14.1` (2024-01-16)](https://github.com/kdeldycke/meta-package-manager/compare/v5.14.0...v5.14.1)

> [!NOTE]
> `5.14.1` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.14.1/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.14.1).

- [bar-plugin] Always call `mpm --version` without color.
- [bar-plugin] Increase robustness of `mpm` version parsing, whether its colored or not.
- [mpm] Temporary disable version output in color to fix already installed plugin/binary pairs. Closes [#1152](https://github.com/kdeldycke/meta-package-manager/pull/1152).

## [`5.14.0` (2024-01-13)](https://github.com/kdeldycke/meta-package-manager/compare/v5.13.1...v5.14.0)

> [!NOTE]
> `5.14.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.14.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.14.0).

- [mpm] Add a `-t`/`--timeout` option to set the maximum duration of each CLI call. Defaults to 10 minutes.
- [mpm] Drop support of Python 3.7.
- [scoop] Fix parsing of Scoop version.
- [mpm] Group platforms by family in the `managers` subcommand.
- [mpm] Run tests and actions on released Python 3.12 version.
- [mpm] Run tests on `macos-13`. Remove tests on `macos-12`, `macos-11`, `ubuntu-20.04` and `windows-2019`.
- [mpm] Run bar plugin unittests in their independent, non-parallel step.
- [mpm] Skip testing on intermediate Python versions to speed up CI. Only the oldest and latest supported.
- [mpm] Skip configuration-related tests while we investigate test isolation.
- [mpm] Fix fetching of full local copy of cask tap in tests to allow for checkout of past formula.
- [mpm] Replace unmaintained `bump2version` by `bump-my-version`.

## [`5.13.1` (2023-05-06)](https://github.com/kdeldycke/meta-package-manager/compare/v5.13.0...v5.13.1)

> [!NOTE]
> `5.13.1` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.13.1/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.13.1).

- [apt] Fix omission of the final result in an `apt` (non-mint) search.
- [mpm] Defaults to case-insensitive, lexicographical sort of package IDs in `backup` subcommand.
- [mpm] Update `brew` installation instructions now that `mpm` is available in official Homebrew repository.

## [`5.13.0` (2023-04-04)](https://github.com/kdeldycke/meta-package-manager/compare/v5.12.0...v5.13.0)

> [!NOTE]
> `5.13.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.13.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.13.0).

- [mpm] Add new `which`/`locate` subcommand to search for CLIs in user's environment.
- [mpm] Allow usage of `sudo` for CLI invocation on all UNIXes, not Linux only. Closes [#976](https://github.com/kdeldycke/meta-package-manager/issues/976).
- [apt] Fix parsing of search results for `apt` and `apt-mint`. Closes [#881](https://github.com/kdeldycke/meta-package-manager/issues/881) and [#966](https://github.com/kdeldycke/meta-package-manager/issues/966).
- [mpm] Adds `--run-destructive`, `--skip-destructive`, `--run-non-destructive` and `--skip-non-destructive` custom options to Pytest.
- [mpm] Run non-destructive tests in parallel and destructive ones in sequential order.
- [mpm] Move all documentation assets to `assets` subfolder.

## [`5.12.0` (2023-02-25)](https://github.com/kdeldycke/meta-package-manager/compare/v5.11.7...v5.12.0)

> [!NOTE]
> `5.12.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.12.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.12.0).

- [mpm] Refactor CLI search to allow all matching to be reported. This will open the way to future support of multiple versions of the same package manager. Refs [#629](https://github.com/kdeldycke/meta-package-manager/issues/629).
- [mpm] Exclude empty files for our CLI search results to skip Microsoft's dummy placeholders on Windows. Closes [#927](https://github.com/kdeldycke/meta-package-manager/issues/927).
- [mpm] Fix composition of CLI search path on Windows.
- [mpm] Deduplicate entries in the list of composed CLI search path.
- [mpm] Do not search for CLI in current directory on Windows.
- [mpm] Fix case-insensitive highlighting of CLI names in path on Windows.
- [yarn] Do not test `yarn` on Linux and Windows.
- [mpm] Do not force test order on Windows.

## [`5.11.7` (2023-02-20)](https://github.com/kdeldycke/meta-package-manager/compare/v5.11.6...v5.11.7)

> [!NOTE]
> `5.11.7` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.11.7/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.11.7).

- [mpm] Fix overlapping detection of `linux` and `wsl2` platforms. Closes [#944](https://github.com/kdeldycke/meta-package-manager/issues/944).
- [pip] Print Python's own version in debug logs before checking for Pip's version.
- [mpm] Code, comments and documentation style change to conform to new QA workflows based on `ruff`.
- [mpm] Produce dependency graph in Mermaid instead of Graphviz. Add new dev dependency on `sphinxcontrib-mermaid`.

## [`5.11.6` (2023-02-12)](https://github.com/kdeldycke/meta-package-manager/compare/v5.11.5...v5.11.6)

> [!NOTE]
> `5.11.6` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.11.6/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.11.6).

- [mpm] Fix collection of artifact files from their folder.

## [`5.11.5` (2023-02-12)](https://github.com/kdeldycke/meta-package-manager/compare/v5.11.4...v5.11.5)

> [!NOTE]
> `5.11.5` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.11.5/).

> [!WARNING]
> `5.11.5` is **not available** on 🐙 GitHub.

- [mpm] Fix collection of artifact files from their folder.

## [`5.11.4` (2023-02-12)](https://github.com/kdeldycke/meta-package-manager/compare/v5.11.3...v5.11.4)

> [!NOTE]
> `5.11.4` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.11.4/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.11.4).

- [mpm] Fix attachment of binaries to GitHub release.

## [`5.11.3` (2023-02-12)](https://github.com/kdeldycke/meta-package-manager/compare/v5.11.2...v5.11.3)

> [!NOTE]
> `5.11.3` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.11.3/).

> [!WARNING]
> `5.11.3` is **not available** on 🐙 GitHub.

- [mpm] Fix attachment of binaries to GitHub release.

## [`5.11.2` (2023-02-11)](https://github.com/kdeldycke/meta-package-manager/compare/v5.11.1...v5.11.2)

> [!NOTE]
> `5.11.2` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.11.2/).

> [!WARNING]
> `5.11.2` is **not available** on 🐙 GitHub.

- [mpm] Refine bug report template.
- [mpm] Fix attachment of binaries to GitHub release.

## [`5.11.1` (2023-02-10)](https://github.com/kdeldycke/meta-package-manager/compare/v5.11.0...v5.11.1)

> [!NOTE]
> `5.11.1` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.11.1/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.11.1).

- [mpm] Remove temporary direct dependency on `charset-normalizer`, fix has been pushed upstream to Nuitka.
- [mpm] Rename artifacts attached to releases to benefits from stable URLs pointing to latest downloads.
- [mpm] Fix some Windows unittests.

## [`5.11.0` (2023-01-30)](https://github.com/kdeldycke/meta-package-manager/compare/v5.10.2...v5.11.0)

> [!NOTE]
> `5.11.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.11.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.11.0).

- [mpm] Unlock run on any Unix-like platform. Closes [#872](https://github.com/kdeldycke/meta-package-manager/issues/872).
- [brew] Activate `brew` on Windows Subsystem for Linux v2.
- [choco] Bump minimal `choco` requirement to `0.10.4`.
- [mpm] Depends on `charset-normalizer < 3` to fix Nuitka compilation.
- [mpm] Run tests on Python `3.12-dev`.
- [mpm] Reduce verbosity of pre-install steps in GitHub actions.
- [mpm] Test `mpm` binaries.
- [mpm] Force upgrade of Ruby on Windows test runners.
- [mpm] Fix installation of old formulae in brew unittests.
- [mpm] Force re-detection of `npm` CLI location on macOS subcommand unittests.
- [mpm] Add new GitHub labels for newly supported platforms.
- [mpm] Generates dependency graph in Graphviz format.

## [`5.10.2` (2022-12-19)](https://github.com/kdeldycke/meta-package-manager/compare/v5.10.1...v5.10.2)

> [!NOTE]
> `5.10.2` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.10.2/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.10.2).

- [mpm] Fix uploading of artifacts to GitHub release.

## [`5.10.1` (2022-12-19)](https://github.com/kdeldycke/meta-package-manager/compare/v5.10.0...v5.10.1)

> [!NOTE]
> `5.10.1` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.10.1/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.10.1).

- [mpm] Fix uploading of Nuitka binaries to GitHub release.

## [`5.10.0` (2022-12-19)](https://github.com/kdeldycke/meta-package-manager/compare/v5.9.0...v5.10.0)

> [!NOTE]
> `5.10.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.10.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.10.0).

- [mpm] Build standalone executable for macOS, Linux and Windows. Closes [#725](https://github.com/kdeldycke/meta-package-manager/issues/725).
- [mpm] Force default output encoding of Windows executable to fix issue on Windows CI agents.
- [bar-plugin] Disable `--bar-plugin-path` option if CLI not installed from sources.
- [bar-plugin] Rename and move `meta_package_manager.7h.py` bar plugin script to eliminate dynamic module loading.
- [mpm] Replace dynamic loading of package manager definition by static code.
- [mpm] Highlight package manager's executable name when printing their path in logs.
- [mpm] Hint at deprecation of manager in the support matrix.
- [mpm] Execute all workflows with Python 3.11.

## [`5.9.0` (2022-11-20)](https://github.com/kdeldycke/meta-package-manager/compare/v5.8.0...v5.9.0)

> [!NOTE]
> `5.9.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.9.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.9.0).

- [pacaur] Implement `pacaur` support. Closes [#816](https://github.com/kdeldycke/meta-package-manager/issues/816).
- [mpm] Allow managers to be flagged as deprecated.
- [apm] Flag `apm` as deprecated.
- [mpm] Remove Atom integration tests.
- [mpm] Fix propagation of user selection of managers in `upgrade` and `remove` subcommands.
- [mpm] Fix production of specifiers in `restore` subcommand.
- [mpm] Fix installation of Scoop on Windows in unittests.
- [mpm] Fix installation of brew on Ubuntu in unittests.
- [mpm] Use form-based issue templates for bug reports and new package manager support requests.
- [mpm] Remove use of deprecated `::set-output` directives and replace them by environment files.

## [`5.8.0` (2022-10-05)](https://github.com/kdeldycke/meta-package-manager/compare/v5.7.0...v5.8.0)

> [!NOTE]
> `5.8.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.8.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.8.0).

- [gem] Implement `remove` operation.
- [mpm] Allow multiple packages to be fed to `install`, `upgrade` and `remove` subcommands.
- [mpm] Allow for a mix of plain, `@`-based and `pkg:`-prefixed purl specifiers on `install`, `upgrade` and `remove` subcommands. Closes [#669](https://github.com/kdeldycke/meta-package-manager/issues/669).
- [mpm] Pass version specifier to `install` operation in `restore` subcommand.
- [mpm] Output warning for `install` and `upgrade_one_cli` operations not implementing version parameter.
- [mpm] Remove GitHub edit link workaround in documentation.

## [`5.7.0` (2022-09-28)](https://github.com/kdeldycke/meta-package-manager/compare/v5.6.2...v5.7.0)

> [!NOTE]
> `5.7.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.7.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.7.0).

- [scoop] Add support for Scoop on Windows. Closes [#546](https://github.com/kdeldycke/meta-package-manager/issues/546).
- [mpm] Fix imports from `click.extra`. Closes [#783](https://github.com/kdeldycke/meta-package-manager/issues/783).

## [`5.6.2` (2022-09-27)](https://github.com/kdeldycke/meta-package-manager/compare/v5.6.1...v5.6.2)

> [!NOTE]
> `5.6.2` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.6.2/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.6.2).

- [mpm] Fix imports from `click.extra`.

## [`5.6.1` (2022-09-26)](https://github.com/kdeldycke/meta-package-manager/compare/v5.6.0...v5.6.1)

> [!NOTE]
> `5.6.1` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.6.1/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.6.1).

- [mpm] Fix import from private `click.extra` submodule.

## [`5.6.0` (2022-09-26)](https://github.com/kdeldycke/meta-package-manager/compare/v5.5.1...v5.6.0)

> [!NOTE]
> `5.6.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.6.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.6.0).

- [brew,cask] Add support for `remove` operation in homebrew.
- [pacman] Fix `pacman` install operation. Closes [#766](https://github.com/kdeldycke/meta-package-manager/pull/766).
- [bar-plugin] Check for minimal Python version.
- [mpm] Run tests on `ubuntu-22.04` and `macos-12`.
- [mpm] Remove tests on `macos-10.15` and `ubuntu-18.04`, they're deprecated by GitHub.
- [mpm] Fix plugin rendering tests.
- [mpm] Always run plugin rendering tests in Poetry venv.
- [bar-plugin] Add a `--check-mpm` option to tests the mpm binary search phase without running a full outdated package listing.
- [mpm] Tests Python and plugin invocation in lots of shell configuration.
- [mpm] Deactivate login shell tests.
- [mpm] Force Homebrew tap repair in tests.
- [mpm] Dynamiccaly get location of Homebrew Cask formulas in tests.
- [mpm] Install `dnf` in tests as of `ubuntu-22.04`. Closes [#563](https://github.com/kdeldycke/meta-package-manager/issues/563).
- [mpm] Add `upgrade_all` operation in support matrix.
- [mpm] Rely on external workflow to set Python version parameters for `mypy`, `black` and `pyupgrade` jobs.

## [`5.5.1` (2022-07-11)](https://github.com/kdeldycke/meta-package-manager/compare/v5.5.0...v5.5.1)

> [!NOTE]
> `5.5.1` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.5.1/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.5.1).

- [mpm] Eliminate rendering of `None` cells to `<null>` in tables.
- [mpm] Add a `--refilter`/`--no-refilter` option to `search` to allow bypassing of `mpm` default refiltering.
- [npm] Implements `remove` operation.
- [npm] Use canonical commands for operations.
- [npm] Reduce output verbosity with `--no-fund` and `--no-audit` options.
- [yarn] Implements `remove` operation.
- [yarn] Fix, document and cleanup all global commands.
- [yarn] Set minimal `yarn` version to `1.20.0`, as it should have been.
- [bar-plugin] Silence all errors but critical ones on `outdated` invocation to prevent a failing manager to block rendering of the plugin output.

## [`5.5.0` (2022-07-08)](https://github.com/kdeldycke/meta-package-manager/compare/v5.4.0...v5.5.0)

> [!NOTE]
> `5.5.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.5.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.5.0).

- [mpm] Restore behavior of having `upgrade` assuming `--all` option on a bare call. Closes [#715](https://github.com/kdeldycke/meta-package-manager/issues/715).
- [cask] Fix parsing of multiple reported installed versions.
- [emerge] Locate and validate `qlist` and `eclean` CLI availability.
- [snap] Fix parsing of empty search results.
- [mpm] Allow package name to be empty instead of duplicating it to package ID.
- [mpm] Keep the operation matrix on the `readme.md` in sync with current code by inspecting implementation.
- [mpm] Add type hints. Closes [#655](https://github.com/kdeldycke/meta-package-manager/issues/655).
- [mpm] Auto-check type hinting in CI.
- [mpm] Render type hints in documentation.
- [mpm] Add metadata for easy citation in academic content.
- [mpm] Deactivate Atom install in macOS tests as it seems broken.

## [`5.4.0` (2022-06-29)](https://github.com/kdeldycke/meta-package-manager/compare/v5.3.0...v5.4.0)

> [!NOTE]
> `5.4.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.4.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.4.0).

- [mpm] Allow global `upgrade` of a subset of packages from the command line if no ambiguity is identified.
- [mpm] Add a `-A`/`--all` option to `upgrade` operation.
- [mpm] Add a `-d`/`--duplicates` option to `installed` operation to only show packages sharing the same ID across multiple managers.
- [mpm] Add a global `--description` option but only implement it for `search` operation.
- [mpm] Always show description for `--extended` search. Closes [#503](https://github.com/kdeldycke/meta-package-manager/issues/503).
- [mpm] Rename `--package-name` search option to `--id-name-only`.
- [mpm] Add operation aliases:
  - `list` → `installed`
  - `uninstall` → `remove`
  - `update` → `upgrade`
  - `lock`/`freeze`/`snapshot` → `backup`
- [mpm] Add a `--merge` option on `backup` operation to update target TOML file with new installed packages.
- [mpm] Add an `--update-version` option on `backup` operation to only update version in the target TOML file.
- [mpm] Add a `--overwrite`/`--force`/`--replace` option on `backup` operation to force TOML overwrite if destination file exists.
- [pipx] Implement `outdated` operation.
- [pip] Do not wait for user confirmation on `remove` operation.
- [mpm] Switch package ID and name columns in table rendering.
- [mpm] Rename all `*-like` labels to `*-based` to help finer identification of families.

## [`5.3.0` (2022-06-25)](https://github.com/kdeldycke/meta-package-manager/compare/v5.2.0...v5.3.0)

> [!NOTE]
> `5.3.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.3.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.3.0).

- [paru] Add `paru` support.
- [pacman,paru,yay] Run `install`, `upgrade`, `remove` and `cleanup` operations with `sudo`.
- [brew,cask] Implement extended search on description.
- [cargo] Implement `remove` operation.
- [mas] Fix parsing of variable-length output in `installed` and `outdated` operations.
- [npm] Apply global variables to all operations.
- [bar-plugin] Fix rendering of package managers without outdated packages. Closes [#631](https://github.com/kdeldycke/meta-package-manager/issues/631).
- [mpm] Colorize version differences in `outdated` operation output.
- [mpm] Add manager homepage URL metadata.
- [mpm] Keep results matching description in `--extended` search mode.
- [mpm] Simplify `installed`, `outdated` and `search` operation by relying on generators and a `package` dataclass.
- [mpm] Disable workflow grouping and concurrency management.

## [`5.2.0` (2022-06-16)](https://github.com/kdeldycke/meta-package-manager/compare/v5.1.0...v5.2.0)

> [!NOTE]
> `5.2.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.2.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.2.0).

- [yay] Add `yay` support. Refs [#527](https://github.com/kdeldycke/meta-package-manager/issues/527).
- [mpm,pacman,pip,pipx] Add `remove` operation.
- [mpm] Add description in search results. Refs [#503](https://github.com/kdeldycke/meta-package-manager/issues/503).
- [mpm] Always refilters search results manually to refine gross matchings.
- [mpm] Document `brew` and Arch Linux installation. Refs [#527](https://github.com/kdeldycke/meta-package-manager/issues/527).
- [mpm] Benchmark distribution of all `mpm` alternatives.
- [mpm] Group workflow jobs so new commits cancels in-progress execution triggered by previous commits.
- [mpm] Run tests on early Python 3.11 releases.

## [`5.1.0` (2022-05-15)](https://github.com/kdeldycke/meta-package-manager/compare/v5.0.1...v5.1.0)

> [!NOTE]
> `5.1.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.1.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.1.0).

- [pipx] Add `pipx` support. Closes [#468](https://github.com/kdeldycke/meta-package-manager/issues/468).
- [cargo] Add `cargo` support. Closes [#633](https://github.com/kdeldycke/meta-package-manager/issues/633).
- [mpm] Factorize search result refiltering code.
- [mpm] Regroup `dnf` and `yum` labels.

## [`5.0.1` (2022-04-28)](https://github.com/kdeldycke/meta-package-manager/compare/v5.0.0...v5.0.1)

> [!NOTE]
> `5.0.1` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.0.1/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.0.1).

- [apt] Fix commands incompatible with `--yes` option. Closes [#625](https://github.com/kdeldycke/meta-package-manager/issues/625).
- [mpm] Add `topgrade` and `pacaptr` in the list of benchmarked alternatives.
- [mpm] Rename `alternative` page to `benchmark`.
- [mpm] Fix label unittests.

## [`5.0.0` (2022-04-25)](https://github.com/kdeldycke/meta-package-manager/compare/v4.13.1...v5.0.0)

> [!NOTE]
> `5.0.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/5.0.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.0.0).

- [zypper] Add `zypper` support for Suse and OpenSuse. Closes [#566](https://github.com/kdeldycke/meta-package-manager/issues/566).
- [emerge] Add `emerge` support.
- [steamcmd] Add `steamcmd` support. Refs [#10](https://github.com/kdeldycke/meta-package-manager/issues/10).
- [yum] Add dedicated `yum` package manager. Refs [#415](https://github.com/kdeldycke/meta-package-manager/issues/415).
- [bar-plugin] Add new `DEFAULT_FONT` and `MONOSPACE_FONT` variable.
- [bar-plugin] Rename all reference of `xbar` to the generic `bar-plugin` label.
- [bar-plugin] Improve search for Python and `mpm` executable.
- [bar-plugin] Restructure the plugin ↔ mpm relationship to delegate all
  plugin layout and rendering logic to `mpm`.
- [bar-plugin] Prevent leaks when modifying environment variables.
- [mpm] Allow `installed` and `outdated` commands to be optionally
  implemented by package managers.
- [mpm] Add new `--plugin-output` option to `outdated` command.
- [mpm] Add `tabulate` as direct dependency and refactor table alignment in
  plugin around it.
- [mpm] Rename `--xbar-plugin-path` option to `--bar-plugin-path`.
- [mpm] Remove `-c`/`--cli-format` option.
- [mpm] Use short-form selection option and fully-qualified path in
  `mpm`-based upgrade-all CLIs produced by `outdated` command.
- [mpm] Add dedicated execution path for running sudo-prefixed commands.
- [mpm] Fix local overriding of CLI parameters leading to missing `sudo`
  pre-command. Closes [#579](https://github.com/kdeldycke/meta-package-manager/issues/579).
- [mpm] Use string highlighting code from `click-extra >= 2.1.0`.
- [mpm] Add edit links to documentation.

## [`4.13.1` (2022-04-17)](https://github.com/kdeldycke/meta-package-manager/compare/v4.13.0...v4.13.1)

> [!NOTE]
> `4.13.1` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/4.13.1/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v4.13.1).

- [apt] Add missing `sudo` pre-commands for `apt` calls that requires it.
  Closes [#496](https://github.com/kdeldycke/meta-package-manager/issues/496) and [#579](https://github.com/kdeldycke/meta-package-manager/issues/579).
- [snap] Fix command argument order. Address [#579](https://github.com/kdeldycke/meta-package-manager/issues/579).
- [bar-plugin] Fix location of `mpm` binary on Apple Silicon machines.
- [mpm] Replace `sphinx_tabs` by `sphinx-design`.
- [mpm] Add SwiftBar plugin screenshots.
- [mpm] Remove date-based shallowing of Homebrew git repository in unittests
  and considers the local runner copy to already be unshallowed.

## [`4.13.0` (2022-04-16)](https://github.com/kdeldycke/meta-package-manager/compare/v4.12.1...v4.13.0)

> [!NOTE]
> `4.13.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/4.13.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v4.13.0).

- [pacman] Add support for `pacman`. Closes [#416](https://github.com/kdeldycke/meta-package-manager/issues/416).
- [apt-mint] Fix search. Closes [#572](https://github.com/kdeldycke/meta-package-manager/issues/572) and [#573](https://github.com/kdeldycke/meta-package-manager/pull/573).
- [apt-mint] Fix `--apt-mint` shortcut option.
- [bar-plugin] Add support for SwiftBar.
- [bar-plugin] Add new `TABLE_RENDERING` option to plugin.
- [bar-plugin] Improve alignment of labels in monospaced font rendering.
- [bar-plugin] Tweak icons.
- [mpm] Allow the `meta_package_manager` module to be directly executed.
- [mpm] Add `--xbar-plugin-path` option.
- [mpm] Fix normalization of CLI arguments.
- [mpm] Fix file not found error on non-Windows platform during version checking.

## [`4.12.1` (2022-04-06)](https://github.com/kdeldycke/meta-package-manager/compare/v4.12.0...v4.12.1)

> [!NOTE]
> `4.12.1` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/4.12.1/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v4.12.1).

- [mpm] Make CLI path evaluation more robust on Windows. Closes [#542](https://github.com/kdeldycke/meta-package-manager/issues/542).

## [`4.12.0` (2022-04-04)](https://github.com/kdeldycke/meta-package-manager/compare/v4.11.0...v4.12.0)

> [!NOTE]
> `4.12.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/4.12.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v4.12.0).

- [dnf] Add support for `dnf`. Closes [#516](https://github.com/kdeldycke/meta-package-manager/issues/516), refs [#415](https://github.com/kdeldycke/meta-package-manager/issues/415).
- [yum] Allow `yum` to act as `dnf`. Closes [#415](https://github.com/kdeldycke/meta-package-manager/issues/415).
- [brew,cask] Fix execution of `sync` command.
- [mpm] Fix extraction of version. Closes [#536](https://github.com/kdeldycke/meta-package-manager/issues/536).

## [`4.11.0` (2022-04-03)](https://github.com/kdeldycke/meta-package-manager/compare/v4.10.0...v4.11.0)

> [!NOTE]
> `4.11.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/4.11.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v4.11.0).

- [brew,cask] Do not let homebrew auto-update on other commands. Refs [#36](https://github.com/kdeldycke/meta-package-manager/issues/36).
- [brew,cask] Disable analytics and env hints in logs.
- [bar-plugin] Fix log verbosity and unittests for xbar plugin.
- [mpm] Show in debug logs the extra environment variable used for CLIs.
- [mpm] Enforce code structure in package manager definition files.
- [mpm] Fix documentation generation.

## [`4.10.0` (2022-03-31)](https://github.com/kdeldycke/meta-package-manager/compare/v4.9.10...v4.10.0)

> [!NOTE]
> `4.10.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/4.10.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v4.10.0).

- [mpm] Allow for package managers to simultaneously set a list of
  pre-commands and environment variables, as well as global arguments before
  and after the custom ones.
- [mpm] Always run unittest in parallel. Adds development dependency on
  `pytest-xdist` and `psutil`.
- [mpm] Use the `tomllib` from the standard library starting with Python
  3.11.
- [mpm] Cap `click-extra` requirement to `<1.7.0` to fix regression. Closes
  [#518](https://github.com/kdeldycke/meta-package-manager/issues/518).

## [`4.9.10` (2022-03-09)](https://github.com/kdeldycke/meta-package-manager/compare/v4.9.9...v4.9.10)

> [!NOTE]
> `4.9.10` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/4.9.10/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v4.9.10).

- [mpm] Fix execution error on Python 3.10 by updating `click-extra`. Closes
  [#467](https://github.com/kdeldycke/meta-package-manager/issues/467).
- [mpm] Reactivate all unittests on Python 3.10.
- [mpm] Remove artificial capping of Python 3.9 to some workflows.
- [mpm] Use external workflow for dependency graph generation and Python code
  modernization.
- [mpm] Remove direct dependency on `cloup`, `simplejson` and `pipdeptree`.

## [`4.9.9` (2022-01-15)](https://github.com/kdeldycke/meta-package-manager/compare/v4.9.8...v4.9.9)

> [!NOTE]
> `4.9.9` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/4.9.9/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v4.9.9).

- [mpm] Fix upload of build artifacts in GitHub release.

## [`4.9.8` (2022-01-15)](https://github.com/kdeldycke/meta-package-manager/compare/v4.9.7...v4.9.8)

> [!NOTE]
> `4.9.8` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/4.9.8/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v4.9.8).

- [mpm] Fix propagation of build artifacts to GitHub release and PyPI.
- [mpm] Fix test of labelling rules.
- [mpm] Remove local dependency on `graphviz` now that fixes were pushed
  upstream.

## [`4.9.7` (2022-01-11)](https://github.com/kdeldycke/meta-package-manager/compare/v4.9.6...v4.9.7)

> [!WARNING]
> `4.9.7` is **not available** on 🐍 PyPI and 🐙 GitHub.

- [mpm] Add release version in artifacts produced by Poetry builds.
- [mpm] Pass local PyPI token to reused workflow to fix publishing.

## [`4.9.6` (2022-01-11)](https://github.com/kdeldycke/meta-package-manager/compare/v4.9.5...v4.9.6)

> [!NOTE]
> `4.9.6` is available on [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v4.9.6).

> [!WARNING]
> `4.9.6` is **not available** on 🐍 PyPI.

- [mpm] Fix detection of Poetry in build workflow.

## [`4.9.5` (2022-01-11)](https://github.com/kdeldycke/meta-package-manager/compare/v4.9.4...v4.9.5)

> [!WARNING]
> `4.9.5` is **not available** on 🐍 PyPI and 🐙 GitHub.

- [mpm] Use external workflow for package building and publishing via Poetry.
- [mpm] Reused external label maintenance workflows and definitions.
- [mpm] Add our custom labels to external syncing workflow.
- [mpm] Auto-label sponsors.
- [mpm] Remove changelog code left-overs.
- [mpm] Aligns content of all PRs locally produced by workflows.

## [`4.9.4` (2022-01-04)](https://github.com/kdeldycke/meta-package-manager/compare/v4.9.3...v4.9.4)

> [!NOTE]
> `4.9.4` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/4.9.4/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v4.9.4).

- [mpm] Re-integrate artifacts in GitHub release on tagging.

## [`4.9.3` (2022-01-04)](https://github.com/kdeldycke/meta-package-manager/compare/v4.9.2...v4.9.3)

> [!NOTE]
> `4.9.3` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/4.9.3/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v4.9.3).

- [mpm] Fix GitHub release's content update.

## [`4.9.2` (2022-01-04)](https://github.com/kdeldycke/meta-package-manager/compare/v4.9.1...v4.9.2)

> [!NOTE]
> `4.9.2` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/4.9.2/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v4.9.2).

- [mpm] Regenerate GitHub release content body dynamiccaly on tagging.

## [`4.9.1` (2022-01-04)](https://github.com/kdeldycke/meta-package-manager/compare/v4.9.0...v4.9.1)

> [!NOTE]
> `4.9.1` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/4.9.1/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v4.9.1).

- [mpm] Automate minor and major version bump.
- [mpm] Automate release preparation workflow.
- [mpm] Trigger tagging, build and version bump on release event.
- [mpm] Add a debug workflow for troubleshooting.

## [`4.9.0` (2022-01-03)](https://github.com/kdeldycke/meta-package-manager/compare/v4.8.0...v4.9.0)

> [!NOTE]
> `4.9.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/4.9.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v4.9.0).

- [mpm] Add single manager selector aliases: `--apm`, `--apt`, `--apt-mint`,
  `--brew`, `--cask`. `--choco`, `--composer`, `--flatpak`, `--gem`, `--mas`,
  `--npm`, `--opkg`, `--pip`, `--snap`, `--vscode` and `--yarn`.
- [brew,cask] Thorough cleanup: call `autoremove` commands to remove unused
  dependencies and use `--prune=all` to scrub the whole cache.
- [mpm] Switch default table rendering to `rounded_outline`.
- [mpm] Rely on `click-extra` for table rendering and tests.
- [mpm] Remove direct dependencies on `click-log` and `cli-helpers`.
- [mpm] Automate post-release version bump.
- [mpm] Outsource some workflow definition to external repository.
- [mpm] Fix generation of dependency graph.

## [`4.8.0` (2021-11-01)](https://github.com/kdeldycke/meta-package-manager/compare/v4.7.0...v4.8.0)

> [!NOTE]
> `4.8.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/4.8.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v4.8.0).

- [mpm] Add `--color`/`--no-color` (aliased to `--ansi`/`--no-ansi`) flags.
- [mpm] Forces no color on JSON output.
- [mpm] Group commands and options in help screen.
- [mpm] Colorize options, choices, metavars and default values in help
  screens.
- [mpm] Reintroduce coloring of `--version` option.
- [mpm] Add dependency on `click-extra`.
- [mpm] Use `sphinx-click` to auto-generate CLI documentation.
- [mpm] Autofix Markdown content with `mdformat`.
- [mpm] Simplify project management by abandoning the dual use of
  `main`/`develop` branches.

## [`4.7.0` (2021-10-13)](https://github.com/kdeldycke/meta-package-manager/compare/v4.6.0...v4.7.0)

> [!NOTE]
> `4.7.0` is available on [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v4.7.0).

> [!WARNING]
> `4.7.0` is **not available** on 🐍 PyPI.

- [mpm] Add help screen coloring.
- [mpm] Change documentation theme from classic RTD to furo.
- [mpm] Move documentation from `readthedocs.org` to `github.io`.
- [mpm] Rewrite documentation from rST to MyST.
- [mpm] Add dependency on `cloup`.
- [mpm] Removes `click-help-colors` dependency.
- [mpm] Run tests on Python 3.10.
- [mpm] Add a contribution guide stub in documentation. Closes [#276](https://github.com/kdeldycke/meta-package-manager/issues/276).

## [`4.6.0` (2021-10-04)](https://github.com/kdeldycke/meta-package-manager/compare/v4.5.0...v4.6.0)

> [!NOTE]
> `4.6.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/4.6.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v4.6.0).

- [mpm] Implements XKCD 1654. Closes [#10](https://github.com/kdeldycke/meta-package-manager/issues/10).
- [mpm] Add `-x`/`--xkcd` option to forces manager selection.
- [mpm] Let `-m`/`--manager` multi-option keep order.

## [`4.5.0` (2021-09-30)](https://github.com/kdeldycke/meta-package-manager/compare/v4.4.0...v4.5.0)

> [!NOTE]
> `4.5.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/4.5.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v4.5.0).

- [choco] Add Chocolatey package manager.
- [mpm] Skip by default the evaluation of package managers not supported on
  the user's platform. Closes [#278](https://github.com/kdeldycke/meta-package-manager/issues/278).
- [mpm] Add a `-a`/`--all-managers` option to force the evaluation of all
  managers.
- [mpm] Fix highlighting of substrings in search results.

## [`4.4.0` (2021-09-27)](https://github.com/kdeldycke/meta-package-manager/compare/v4.3.0...v4.4.0)

> [!NOTE]
> `4.4.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/4.4.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v4.4.0).

- [mpm] Add a global `-d`/`--dry-run` option.
- [apt] Add dedicated `apt-mint` manager to handle the special case of `apt`
  on Linux Mint.
- [bar-plugin] Let xbar plugin check minimal mpm version requirement.
- [mpm] Use regexpes to extract package manager versions.
- [mpm] Add beta `windows-2022` CI/CD build target.
- [mpm] Remove all the unused utilities to discard some table rendering on
  Windows.

## [`4.3.0` (2021-09-25)](https://github.com/kdeldycke/meta-package-manager/compare/v4.2.0...v4.3.0)

> [!NOTE]
> `4.3.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/4.3.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v4.3.0).

- [mpm] Add new `install` command. Closes [#21](https://github.com/kdeldycke/meta-package-manager/issues/21).
- [vscode] Add support for Visual Studio Code plugins.
- [mpm] Finish complete `restore` command implementation. Closes [#38](https://github.com/kdeldycke/meta-package-manager/issues/38).
- [mpm] Remove un-enforced poetry-like caret-based version specification from
  TOML backup files.
- [mpm] Forces logger state reset before each CLI call in unittests.

## [`4.2.0` (2021-09-21)](https://github.com/kdeldycke/meta-package-manager/compare/v4.1.0...v4.2.0)

> [!NOTE]
> `4.2.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/4.2.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v4.2.0).

- [mpm] Add support for TOML configuration file. Closes [#66](https://github.com/kdeldycke/meta-package-manager/issues/66).
- [mpm] Add `-C`/`--config` option to point to specific configuration file.
- [mpm] Upgrade to Click 8.x.
- [mpm] Add support for `psql_unicode` and `minimal` table format.
- [mpm] Set default table format to `psql_unicode` instead of `fancy_grid` to
  reduce visual noise.
- [mpm] Add support for environment variables for all parameters, prefixed
  with `MPM_`.
- [mpm] Let Click produce default values in help screen.
- [mpm] Replace `tomlkit` dependency by `tomli` and `tomli_w`.
- [bar-plugin] Fix xbar plugin output format.
- [bar-plugin] Rename `VAR_SUBMENU_lAYOUT` environment variable to
  `VAR_SUBMENU_LAYOUT`.
- [mpm] Remove support for `--cli-format bitbar` option. Use `xbar` value
  instead.

## [`4.1.0` (2021-05-01)](https://github.com/kdeldycke/meta-package-manager/compare/v4.0.0...v4.1.0)

> [!NOTE]
> `4.1.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/4.1.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v4.1.0).

- [bar-plugin] Add new `Submenu layout` boolean option in xbar plugin UI.
- [bar-plugin] Rename `XBAR_MPM_SUBMENU` environment variable to
  `VAR_SUBMENU_lAYOUT`.
- [mpm] Allow search of multiple CLI names for a package manager.
- [pip] Fix search of `python3` binary on macOS. Closes [#247](https://github.com/kdeldycke/meta-package-manager/issues/247).

## [`4.0.0` (2021-04-27)](https://github.com/kdeldycke/meta-package-manager/compare/v3.6.0...v4.0.0)

> [!NOTE]
> `4.0.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/4.0.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v4.0.0).

- [bar-plugin] Upgrade BitBar plugin to new xbar format.
- [bar-plugin] Drop xbar plugin requirement on Python 2.x and bump it up to Python
  3.7.3.
- [bar-plugin] Update references of BitBar to xbar.
- [bar-plugin] Rename `BITBAR_MPM_SUBMENU` environment variable to
  `XBAR_MPM_SUBMENU`.
- [mpm] Rename `--cli-format bitbar` option to `--cli-format xbar`.
- [mpm] Auto-generate API documentation via a GitHub action workflow.
- [mpm] Only trigger dependency graph update on tagging to reduce noise.
- [mpm] Re-introduce `isort`.

## [`3.6.0` (2021-01-03)](https://github.com/kdeldycke/meta-package-manager/compare/v3.5.2...v3.6.0)

> [!NOTE]
> `3.6.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/3.6.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v3.6.0).

- [brew] Add support for `brew` on Linux.
- [brew,cask] Bump minimal requirement of `brew` to `2.7.0`.
- [cask] Address deprecation of `cask` CLI subcommands.
- [pip] `pip search` has been disabled by maintainers because of server-side
  high-load.
- [mpm] Add test runs against new OSes and distributions: `ubuntu-18.04` and
  `macos-11.0`.
- [mpm] Remove `pycodestyle` now that we rely on `black`.
- [mpm] Add emoji to issue labels.

## [`3.5.2` (2020-10-29)](https://github.com/kdeldycke/meta-package-manager/compare/v3.5.1...v3.5.2)

> [!NOTE]
> `3.5.2` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/3.5.2/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v3.5.2).

- [mpm] Run tests on Python 3.9.
- [mpm] Upgrade to `Poetry 1.1.0`.
- [mpm] Colorize version screen and add debug data.
- [mpm] Test publishing to PyPI in dry-run mode by the way of Poetry.
- [mpm] Make all keyword-based choice parameters (`--manager`, `--exclude`,
  `--output-format`, `--sort-by` and `--cli-format`) case-insensitive.
- [mpm] Pin versions of OSes and distributions in CI workflows to
  `ubuntu-20.04`, `macos-10.15` and `windows-2019`.
- [mpm] Always print errors in unittest's CLI calls.
- [mpm] Slow-down tests to prevent PyPI rate-limiting on live API.
- [mpm] Fix `brew` setup on macOS CI runners.
- [mpm] Fix `npm` setup in Ubuntu 18.04 and 20.04 CI runners.
- [mpm] Use latest `Atom` version in Ubuntu CI runners.

## [`3.5.1` (2020-10-03)](https://github.com/kdeldycke/meta-package-manager/compare/v3.5.0...v3.5.1)

> [!NOTE]
> `3.5.1` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/3.5.1/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v3.5.1).

- [mpm] Defaults to `--continue-on-error` instead of stopping.
- [mpm] Force checking of CLI being a file.
- [mpm] Auto-optimize images.
- [mpm] Auto-lock closed issues and PRs after a moment of inactivity.

## [`3.5.0` (2020-09-20)](https://github.com/kdeldycke/meta-package-manager/compare/v3.4.2...v3.5.0)

> [!NOTE]
> `3.5.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/3.5.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v3.5.0).

- [mpm] Fix `--stop-on-error` parameter: it was never taken into account.
- [brew,cask] Bump minimal requirement of `brew` to `2.5.0`.
- [brew,cask] Fix warning to deprecated options.
- [npm] Always fix JSON parsing on error for any npm subcommand.

## [`3.4.2` (2020-09-13)](https://github.com/kdeldycke/meta-package-manager/compare/v3.4.1...v3.4.2)

> [!NOTE]
> `3.4.2` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/3.4.2/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v3.4.2).

- [brew,cask] Do not mix-up brew and cask upgrades.
- [npm] Skip parsing of JSON results on error.

## [`3.4.1` (2020-09-02)](https://github.com/kdeldycke/meta-package-manager/compare/v3.4.0...v3.4.1)

> [!NOTE]
> `3.4.1` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/3.4.1/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v3.4.1).

- [mpm] Rename `master` branch to `main`.

## [`3.4.0` (2020-08-18)](https://github.com/kdeldycke/meta-package-manager/compare/v3.3.0...v3.4.0)

> [!NOTE]
> `3.4.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/3.4.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v3.4.0).

- [yarn] Set minimal requirement to `1.20.0`.
- [yarn] Fix deprecated global arguments.
- [bar-plugin] Force refresh of local package databases before fetching outdated
  ones.
- [mpm] Add utilities to read a config TOML file. Refs [#66](https://github.com/kdeldycke/meta-package-manager/issues/66).
- [mpm] Auto-format Python code with Black.
- [mpm] Move `pytest` config from `setup.py` to `pyproject.toml`.
- [mpm] Removes `isort`.
- [mpm] Auto-update Python's dependencies.
- [mpm] Auto-update GitHub actions.
- [mpm] Auto-update `.gitignore` file.
- [mpm] Auto-update `.mailmap` file.
- [mpm] Lint all YAML files. Add dependency on `yamllint` package.
- [mpm] Removes `requires.io` and Scrutinizer badges.
- [mpm] Revert to `pipdeptree` to produce package dependency graph.

## [`3.3.0` (2020-06-23)](https://github.com/kdeldycke/meta-package-manager/compare/v3.2.0...v3.3.0)

> [!NOTE]
> `3.3.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/3.3.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v3.3.0).

- [bar-plugin] Each entry in the drop-down menu can now be called into a terminal
  to track the execution by holding the `Option` key.
- [bar-plugin] Fix rendering of upgrade CLI in Bitbar dialect.
- [mpm] Hint for lack of `sync` and `cleanup` support by managers.
- [mpm] Do not print table headers if there is no row to print.
- [mpm] Always print non-fatal `<stderr>` output as warning mode.
- [mpm] Skip table rendering tests if no table is printed to stdout. Fixes
  flacky tests.
- [mpm] Replace internal helpers with upstreamed `boltons 20.2.0` utils.
- [mpm] Force test marked as `xfail` count as failure if they succeed.
- [mpm] Always check wheel content.
- [mpm] Automate creation of GitHub release.
- [mpm] Automate publishing of package to PyPI on tagging.
- [mpm] Save build artifacts on each CI runs.
- [mpm] Auto-sort module imports.
- [mpm] Auto-fix common typos.
- [mpm] Lint JSON files.
- [mpm] Automate GitHub label generation and synchronization.
- [mpm] Automatically applies labels on PRs and issues depending on their
  changed files and content.
- [mpm] Check label rules against manager definitions. Adds development
  dependency on `PyYAML`.

## [`3.2.0` (2020-05-31)](https://github.com/kdeldycke/meta-package-manager/compare/v3.1.0...v3.2.0)

> [!NOTE]
> `3.2.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/3.2.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v3.2.0).

- [snap] Add support for `snap` on Linux.
- [cask] Rely on JSON output to fetch outdated packages.
- [brew,cask] Bump minimal requirement to 2.2.15.
- [pip] Remove `pip2`/`pip3` distinctions, use system's python and call `pip`
  module.
- [windows] Allow discarding of some table rendering on Windows.
- [mpm] Add `--time`/`--no-time` flag to show elapsed execution time. Closes
  [#9](https://github.com/kdeldycke/meta-package-manager/issues/9).
- [mpm] Print table rendering, stats and timing in console output instead of
  logger to allow them to be greppable.
- [bar-plugin] Test plugin with Python 2.7.
- [mpm] Allow for manager-specific search path to help hunting down CLIs.
- [mpm] Highlight CLI and indent results in debug output.
- [mpm] Bump dependency to `pylint 2.5` and `cli-helpers 2.0`.
- [mpm] Use local copy of `boltons` utils while we wait for upstream release.
- [mpm] Move pylint config from `setup.cfg` to `pyproject.toml`.
- [mpm] Fail CI and QA checks if pylint score lower than 9.
- [mpm] Add more platform definition unittests.
- [mpm] Unittests all rendering modes in all subcommands.
- [mpm] Randomize unittests.
- [mpm] Drop support of Python 3.6.
- [mpm] Use group-tabs in Sphinx docs.

## [`3.1.0` (2020-04-02)](https://github.com/kdeldycke/meta-package-manager/compare/v3.0.0...v3.1.0)

> [!NOTE]
> `3.1.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/3.1.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v3.1.0).

- [mpm] Add new `cleanup` command. Closes [#5](https://github.com/kdeldycke/meta-package-manager/issues/5).
- [mpm] Improve table sorting with new version-aware tokenizer.
- [mpm] Highlight manager IDs depending on their availability in `managers`
  command.
- [gem] Ignore `default:` prefix on package version parsing.
- [mpm] Remove `packaging` dependency. Rely on internal version parsing.
- [mpm] Add new `--exact` and `--extended` parameters to `search` command.
- [mpm] Highlight search matches in console output.
- [mas] Retrieve version in search results.
- [mas] Bump minimal version to `1.6.1`.
- [mpm] Allow stats to be printed for `backup` command.
- [gem] Bump minimal requirement to `2.5.0`.

## [`3.0.0` (2020-03-25)](https://github.com/kdeldycke/meta-package-manager/compare/v2.9.0...v3.0.0)

> [!NOTE]
> `3.0.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/3.0.0/) and [🐙 GitHub](https://github.com/kdeldycke/meta-package-manager/releases/tag/v3.0.0).

- [mpm] Add new `backup` and dummy `restore` commands to respectively dump
  and load up list of installed packages to/from a TOML file. Refs [#38](https://github.com/kdeldycke/meta-package-manager/issues/38).
- [mpm] Add dependency on `tomlkit`.
- [yarn] Add support for `yarn` package manager for Linux, macOS and Windows.
- [yarn] Install yarn on all unittest platforms.
- [mpm] Allow exclusion of a subset of package managers. Closes [#45](https://github.com/kdeldycke/meta-package-manager/issues/45).
- [pip] Collect installer metadata on listing.
- [pip] Bump minimal requirement of `pip` to `10.0.*`.
- [mpm] Prepend `/usr/local/bin` to cli search path.
- [npm] `install package@version` instead of `update package`.
- [npm] Skip update notifier.
- [brew,cask] Allow independent search for each manager.
- [brew,cask] Bump minimal requirement of to `2.2.9`.
- [mpm] Allow sorting restuls by packages, managers or version. Closes
  [#35](https://github.com/kdeldycke/meta-package-manager/issues/35) and [#37](https://github.com/kdeldycke/meta-package-manager/pull/37).
- [mpm] Add shell completion for Bash, Zsh and Fish.
- [mpm] Do not force sync when calling outdated. Closes [#36](https://github.com/kdeldycke/meta-package-manager/issues/36).
- [apt] Fallback on `apt version apt` when looking for version. Closes
  [#57](https://github.com/kdeldycke/meta-package-manager/pull/57) and [#52](https://github.com/kdeldycke/meta-package-manager/issues/52).
- [mpm] Removes all copyright dates.
- [mpm] Replace unmaintained `bumpversion` by `bump2version`.
- [mpm] Raise requirement to `click 7.1`.
- [mpm] Raise requirement to `boltons >= 20.0`.

## [`2.9.0` (2020-03-18)](https://github.com/kdeldycke/meta-package-manager/compare/v2.8.0...v2.9.0)

> [!NOTE]
> `2.9.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/2.9.0/).

- [mpm] Drop support of Python 2.7, 3.4 and 3.5. Add support for Python 3.8.
- [windows] Add support for `apm`, `composer`, `gem`, `npm` and `pip2` on
  Windows.
- [linux] Add support for `Flatpak` and `opkg` package managers on Linux.
- [gem] Force Ruby `gem` to install packages to user-install by default. Refs
  [#58](https://github.com/kdeldycke/meta-package-manager/issues/58).
- [pip] Force Python `pip` upgrade to user-installed packages. Refs [#58](https://github.com/kdeldycke/meta-package-manager/pull/58).
- [brew] Fix call to `brew upgrade --cleanup`. Refs [#50](https://github.com/kdeldycke/meta-package-manager/issues/50).
- [brew] Fix parsing of `brew` version. Closes [#49](https://github.com/kdeldycke/meta-package-manager/issues/49) and [#51](https://github.com/kdeldycke/meta-package-manager/pull/51).
- [mpm] Switch from Travis to GitHub actions.
- [composer] Install `composer` in all platforms CI runners.
- [linux] Install `flatpak` in Linux CI runner.
- [windows] Install `apm` in Windows CI runner.
- [mpm] Bump requirement to `click-log >= 0.3`.
- [mpm] Add non-blocking Pylint code quality checks in CI.
- [mpm] Check for conflicting dependencies in CI.
- [mpm] Use Poetry for package and virtualenv management.
- [mpm] Replace `pipdeptree` by Poetry CLI output.
- [mpm] Remove `backports.shutil_which` dependency.
- [mpm] Update `.gitignore`.
- [mpm] Drop all Python 3.0 `__future__` imports.
- [mpm] Add detailed usage CLI page in documentation.

## [`2.8.0` (2019-01-03)](https://github.com/kdeldycke/meta-package-manager/compare/v2.7.0...v2.8.0)

> [!NOTE]
> `2.8.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/2.8.0/).

- [composer] Add support for PHP `composer`.
- [cask] Remove `cask`-specific `version`, `sync` and `search` command.
  Closes [#47](https://github.com/kdeldycke/meta-package-manager/issues/47).
- [brew] Vanilla brew and cask CLIs now shares the same version requirements.
- [brew] Bump minimal requirement of `brew` and `cask` to `1.7.4`.
- [mpm] Activate unittests in Python 3.7.
- [mpm] Drop Travis unittests on deprecated Ubuntu Precise targets and
  vintage Mac OS X 10.10 and 10.11.
- [mpm] Use latest macOS 10.12 and 10.13 Travis images.

## [`2.7.0` (2018-04-02)](https://github.com/kdeldycke/meta-package-manager/compare/v2.6.1...v2.7.0)

> [!NOTE]
> `2.7.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/2.7.0/).

- [mpm] Add new `--ignore-auto-updates` and `--include-auto-updates` boolean
  flags.
- [mpm] Support even fancier table output rendering, including `csv` and
  `html`.
- [mpm] Depends on `cli-helpers` package to render tables.
- [mpm] Removes direct dependency on `tabulate`.
- [cask] Fix minimal version check for `cask`. Closes [#41](https://github.com/kdeldycke/meta-package-manager/issues/41) and
  [#44](https://github.com/kdeldycke/meta-package-manager/pull/44).
- [bar-plugin] Do not run BitBar plugin unittests but on macOS.

## [`2.6.1` (2017-11-05)](https://github.com/kdeldycke/meta-package-manager/compare/v2.6.0...v2.6.1)

> [!NOTE]
> `2.6.1` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/2.6.1/).

- [mpm] Fix Travis unittests.

## [`2.6.0` (2017-09-10)](https://github.com/kdeldycke/meta-package-manager/compare/v2.5.0...v2.6.0)

> [!NOTE]
> `2.6.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/2.6.0/).

- [apt] Add support for `apt` on Linux systems.
- [pip] Use pip 9.0 JSON output. Closes [#18](https://github.com/kdeldycke/meta-package-manager/issues/18).
- [pip] Bump minimal requirement of `pip` to `9.0.*`.
- [cask] Use new `brew cask outdated` command.
- [cask] Remove usage of deprecated `brew cask update` command.
- [cask] Bump minimal requirement of `cask` to `1.1.12`.
- [mpm] Add dependency on `simplejson`.
- [mpm] Bump requirement to `click_log >= 0.2.0`. Closes [#39](https://github.com/kdeldycke/meta-package-manager/issues/39).
- [mpm] Replace `nose` by `pytest`.
- [mpm] Only notify by mail of test failures.

## [`2.5.0` (2017-03-01)](https://github.com/kdeldycke/meta-package-manager/compare/v2.4.0...v2.5.0)

> [!NOTE]
> `2.5.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/2.5.0/).

- [mpm] Auto-detect location of manager CLI on the system.
- [mpm] Add new `search` operation. Closes [#22](https://github.com/kdeldycke/meta-package-manager/issues/22).
- [npm] Bump minimal requirement of `npm` to `4.0.*`.
- [mpm] Rename `list` operation to `installed`.
- [apm,gem,linux,npm] Allow use of `apm`, `gem` and `npm` managers on Linux.
- [mpm] Add new `--stats`/`--no-stats` boolean flags. Closes [#8](https://github.com/kdeldycke/meta-package-manager/issues/8).
- [mpm] Add new `--stop-on-error`/`--continue-on-error` parameters to make
  CLI errors either blocking or non-blocking.
- [mpm] Allow reporting of several CLI errors by managers.
- [mpm] Allow selection of a subset of managers.
- [mpm] Do not force a `sync` before listing installed packages in CLI.
- [mpm] Rework API documentation.
- [cask] Add unittest to cover unicode names for Cask packages. Closes
  [#16](https://github.com/kdeldycke/meta-package-manager/issues/16).
- [cask] Add unittest to cover Cask packages with multiple names. Refs
  [#26](https://github.com/kdeldycke/meta-package-manager/issues/26).
- [mpm] Drop support of Python 3.3.

## [`2.4.0` (2017-01-28)](https://github.com/kdeldycke/meta-package-manager/compare/v2.3.0...v2.4.0)

> [!NOTE]
> `2.4.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/2.4.0/).

- [mpm] Add new `list` operation. Closes [#20](https://github.com/kdeldycke/meta-package-manager/issues/20).
- [mas] Fix upgrade of `mas` packages. Closes [#32](https://github.com/kdeldycke/meta-package-manager/issues/32).
- [bar-plugin] Document BitBar plugin release process.
- [mpm] Colorize check-marks in CLI output.
- [mpm] Decouple `sync` and `outdated` actions in all managers.
- [mpm] Cache output of `outdated` command.
- [mpm] Add global todo list in documentation.
- [mpm] Bump requirement to `boltons >= 17.0.0` for Python 3.3 compatibility.

## [`2.3.0` (2017-01-15)](https://github.com/kdeldycke/meta-package-manager/compare/v2.2.0...v2.3.0)

> [!NOTE]
> `2.3.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/2.3.0/).

- [mpm] Add Sphinx documentation. Closes [#24](https://github.com/kdeldycke/meta-package-manager/issues/24).
- [mpm] Add installation instructions. Closes [#19](https://github.com/kdeldycke/meta-package-manager/issues/19).
- [mpm] Add a list of *Falsehoods Programmers Believe About Package
  Managers*.
- [mpm] Add a `.mailmap` config file to consolidate contributor's identity.
- [bar-plugin] Make it easier to change the font, size and color of text in
  BitBar plugin.
- [bar-plugin] Move error icon in BitBar plugin to the front of manager name.
- [cask] Fix parsing of `cask` packages with multiple names. Closes
  [#26](https://github.com/kdeldycke/meta-package-manager/issues/26).
- [bar-plugin] Move BitBar plugin documentation to dedicated page.
- [mpm] Fix exceptions when commands gives no output. Closes [#29](https://github.com/kdeldycke/meta-package-manager/issues/29) and
  [#31](https://github.com/kdeldycke/meta-package-manager/pull/31).
- [cask] Fix `cask update` deprecation warning. Closes [#28](https://github.com/kdeldycke/meta-package-manager/issues/28).
- [mpm] Activate unittests in Python 3.6.
- [mpm] Replace double by single-width characters in `mpm` output to fix
  table misalignment. Closes [#30](https://github.com/kdeldycke/meta-package-manager/issues/30).

## [`2.2.0` (2016-12-25)](https://github.com/kdeldycke/meta-package-manager/compare/v2.1.1...v2.2.0)

> [!NOTE]
> `2.2.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/2.2.0/).

- [mpm] Rename `supported` property of managers to `fresh`.
- [mpm] Allow restriction of package managers to a platform. Closes
  [#7](https://github.com/kdeldycke/meta-package-manager/issues/7).
- [mpm] Include `supported` property in `mpm managers` sub-command.
- [bar-plugin] Add optional submenu rendering for BitBar plugin. Closes [#23](https://github.com/kdeldycke/meta-package-manager/pull/23).
- [bar-plugin] Move `Upgrade all` menu entry to the bottom of each section in
  BitBar plugin.
- [pip] Allow destructive unittests in Travis CI jobs.
- [pip] Allow usage of `pip2` and `pip3` managers on Linux.
- [mpm] Print current platform in debug messages.
- [mpm] Unittest detection of managers on each platform.

## [`2.1.1` (2016-12-17)](https://github.com/kdeldycke/meta-package-manager/compare/v2.1.0...v2.1.1)

> [!NOTE]
> `2.1.1` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/2.1.1/).

- [brew,cask] Fix parsing of non-point releases of `brew` and `cask`
  versions. Closes [#15](https://github.com/kdeldycke/meta-package-manager/issues/15).
- [bar-plugin] Do not render emoji in BitBar plugin menu entries.
- [bar-plugin] Do not trim error messages rendered in BitBar plugin.
- [mpm] Do not strip CLI output. Keep original format.
- [mpm] Fix full changelog link.

## [`2.1.0` (2016-12-14)](https://github.com/kdeldycke/meta-package-manager/compare/v2.0.0...v2.1.0)

> [!NOTE]
> `2.1.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/2.1.0/).

- [bar-plugin] Adjust rendering of BitBar plugin errors.
- [mpm] Fix fetching of log level names in Python 3.4+.
- [mpm] Print CLI output in unittests.
- [mpm] Print more debug info in unittests when CLI produce tracebacks.
- [macos] Drop support and unittests on Mac OS X 10.9.
- [macos] Add new macOS 10.12 target for Travis CI builds.
- [bar-plugin] Move BitBar plugin within the Python module.
- [mpm] Show unmet version requirements in table output for `mpm managers`
  sub-command.
- [mpm] Fix duplicates in outdated packages by indexing them by ID.
- [bar-plugin] Unittest simple call of BitBar plugin.
- [mpm] Always print the raw, un-normalized version of managers, as reported
  by themselves.
- [mpm] Fetch version of all managers.
- [mpm] Make manager version mandatory.
- [mpm] Bump requirement to `readme_renderer >= 16.0`.
- [mpm] Always remove ANSI codes from CLI output.
- [mpm] Fix rendering of unicode logs.
- [mpm] Bump requirement to `click_log >= 0.1.5`.
- [bar-plugin] Force `LANG` environment variable to `en_US.UTF-8`.
- [bar-plugin,mpm] Share same code path for CLI execution between `mpm` and
  BitBar plugin.
- [mpm] Add a `-d`/`--dry-run` option to `mpm upgrade` sub-command.
- [macos] Remove hard-requirement on `macOS` platform. Refs [#7](https://github.com/kdeldycke/meta-package-manager/issues/7).
- [macos,mpm] Fix upgrade of `setuptools` in `macOS` and Python 3.3 Travis
  jobs.

## [`2.0.0` (2016-12-04)](https://github.com/kdeldycke/meta-package-manager/compare/v1.12.0...v2.0.0)

> [!NOTE]
> `2.0.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/2.0.0/).

- [bar-plugin] Rewrite BitBar plugin based on `mpm`. Closes [#13](https://github.com/kdeldycke/meta-package-manager/issues/13).
- [bar-plugin] Render errors with a monospaced font in BitBar plugin.
- [mpm] Add missing `CHANGES.rst` in `MANIFEST.in`.
- [mpm] Make wheels generated under Python 2 environnment available for
  Python 3 too.
- [mpm] Only show latest changes in the long description of the package
  instead of the full changelog.
- [mpm] Add link to full changelog in package's long description.
- [mpm] Bump trove classifiers status out of beta.
- [mpm] Fix package keywords.
- [mpm] Bump minimal `pycodestyle` requirement to 2.1.0.
- [mpm] Always check for package metadata in Travis CI jobs.
- [mpm] Add `upgrade_all_cli` field for each package manager in JSON output
  of `mpm outdated` command.

## [`1.12.0` (2016-12-03)](https://github.com/kdeldycke/meta-package-manager/compare/v1.11.0...v1.12.0)

> [!NOTE]
> `1.12.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/1.12.0/).

- [mpm] Rename `mpm update` command to `mpm upgrade`.
- [mpm] Allow restriction to only one package manager for each sub-command.
  Closes [#12](https://github.com/kdeldycke/meta-package-manager/issues/12).
- [mpm] Differentiate packages names and IDs. Closes [#11](https://github.com/kdeldycke/meta-package-manager/issues/11).
- [mpm] Sort list of outdated packages by lower-cased package names first.
- [mpm] Add `upgrade_cli` field for each outdated packages in JSON output.
- [bar-plugin,mpm] Allow user to choose rendering of `upgrade_cli` field to
  either one-liner, fragments or BitBar format. Closes [#14](https://github.com/kdeldycke/meta-package-manager/issues/14).
- [mpm] Include errors reported by each manager in JSON output of
  `mpm outdated` command.
- [cask] Fix parsing of multiple versions of `cask` installed packages.
- [brew,cask] Fix lexicographical sorting of `brew` and `cask` package
  versions.
- [mpm] Fix fall-back to iterative full upgrade command.
- [mpm] Fix computation of outdated packages statistics.

## [`1.11.0` (2016-11-30)](https://github.com/kdeldycke/meta-package-manager/compare/v1.10.0...v1.11.0)

> [!NOTE]
> `1.11.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/1.11.0/).

- [mpm] Allow rendering of output data into `json`.
- [mpm] Sort list of outdated packages by lower-cased package IDs.
- [brew,cask] Bump minimal requirement of `brew` to 1.0.0 and `cask` to
  1.1.0.
- [cask] Fix fetching of outdated `cask` packages.
- [cask] Fix upgrade of `cask` packages.

## [`1.10.0` (2016-10-04)](https://github.com/kdeldycke/meta-package-manager/compare/v1.9.0...v1.10.0)

> [!NOTE]
> `1.10.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/1.10.0/).

- [mpm] Add optional `version` property on package manager definitions.
- [mpm] Allow each package manager to set requirement on its own version.
- [mas] Let `mas` report its own version.
- [mas] Bump minimal requirement of `mas` to 1.3.1.
- [mas] Fetch currently installed version from `mas`. Closes [#4](https://github.com/kdeldycke/meta-package-manager/issues/4).
- [mas] Fix parsing of `mas` package versions after the 1.3.1 release.
- [mpm] Cache lazy properties to speed metadata computation.
- [mpm] Shows detailed state of package managers in CLI.

## [`1.9.0` (2016-09-23)](https://github.com/kdeldycke/meta-package-manager/compare/v1.8.0...v1.9.0)

> [!NOTE]
> `1.9.0` is available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/1.9.0/).

- [mpm] Fix `bumpversion` configuration to target `CHANGES.rst` instead of
  `README.rst`.
- [mpm] Render list of detected managers in a table.
- [macos] Use `conda` in Travis tests to install specific versions of Python
  across the range of macOS workers.
- [macos] Drop support for PyPy while we search a way to install it on macOS
  with Travis.
- [mpm] Let `mpm` auto-detect package manager definitions.
- [mpm] Show package manager IDs in `mpm managers` CLI output.
- [mpm] Rename `package_manager.7h.py` BitBar plugin to
  `meta_package_manager.7h.py`.
- [mpm] Give each package manager its own dedicated short string ID.
- [mpm] Keep a cache of instantiated package manager.
- [mpm] Add unittests around package manager definitions.
- [mpm] Do not display location of inactive managers, even if hard-coded.
- [mpm] Split-up CLI-producing methods and CLI running methods in
  `PackageManager` base class.
- [mpm] Add a new `update` CLI sub-command.
- [mpm] Add a new `sync` CLI sub-command.
- [mpm] Rename managers' `active` property to `available`.
- [mpm] Move all package manager definitions in a dedicated folder.
- [mpm] Add simple CLI unittests. Closes [#2](https://github.com/kdeldycke/meta-package-manager/issues/2).
- [mpm] Implement `outdated` CLI sub-command.
- [mpm] Allow selection of table rendering.
- [cask] Fix parsing of unversioned cask packages. Closes [#6](https://github.com/kdeldycke/meta-package-manager/pull/6).

## [`1.8.0` (2016-08-22)](https://github.com/kdeldycke/meta-package-manager/compare/v1.7.0...v1.8.0)

> [!NOTE]
> `1.8.0` is the *first version* available on [🐍 PyPI](https://pypi.org/project/meta-package-manager/1.8.0/).

- [mpm] Move the plugin to its own repository.
- [mpm] Rename `package-manager` project to `meta-package-manager`.
- [mpm] Add a `README.rst` file.
- [mpm] License under GPLv2+.
- [mpm] Add `.gitignore` config.
- [mpm] Add Python package skeleton. Closes [#1](https://github.com/kdeldycke/meta-package-manager/issues/1).
- [mpm] Split `CHANGES.rst` out of `README.rst`.
- [mpm] Add Travis CI configuration.
- [mpm] Use semver-like 3-components version number.
- [bar-plugin] Copy all BitBar plugin code to Python module.
- [mpm] Give each supported package manager its own module file.
- [mpm] Add minimal `mpm` meta CLI to list supported package managers.
- [mpm] Add default `bumpversion`, `isort`, `nosetests`, `coverage`, `pep8`
  and `pylint` default configuration.

## [`1.7.0` (2016-08-16)](https://github.com/kdeldycke/meta-package-manager/compare/v1.6.0...v1.7.0)

- [brew] Fix issues with `$PATH` not having Homebrew/Macports.
- [pip] New workaround for full `pip` upgrade command.
- [cask] Workaround for Homebrew Cask full upgrade command.
- [mpm] Grammar fix when 0 packages need to be upgraded.

## [`1.6.0` (2016-08-10)](https://github.com/kdeldycke/meta-package-manager/compare/v1.5.0...v1.6.0)

- [pip] Work around the lacks of full `pip` upgrade command.
- [mpm] Fix `UnicodeDecodeError` on parsing CLI output.

## [`1.5.0` (2016-07-25)](https://github.com/kdeldycke/meta-package-manager/compare/v1.4.0...v1.5.0)

- [mas] Add support for `mas`.
- [mpm] Don't show all `stderr` as `err` (check return code for error state).

## [`1.4.0` (2016-07-10)](https://github.com/kdeldycke/meta-package-manager/compare/v1.3.0...v1.4.0)

- [mpm] Don't attempt to parse empty lines.
- [npm] Check for linked `npm` packages.
- [gem] Support system or Homebrew Ruby Gems (with proper `sudo` setup).

## [`1.3.0` (2016-07-09)](https://github.com/kdeldycke/meta-package-manager/compare/v1.2.0...v1.3.0)

- [mpm] Add changelog.
- [mpm] Add reference to package manager's issues.
- [cask] Force Cask update before evaluating available packages.
- [mpm] Add sample of command output as version parsing can be tricky.

## [`1.2.0` (2016-07-08)](https://github.com/kdeldycke/meta-package-manager/compare/v1.1.0...v1.2.0)

- [apm,gem,npm,pip] Add support for both `pip2` and `pip3`, Node's `npm`,
  Atom's `apm`, Ruby's `gem`.
- [cask] Fixup `brew cask` checking.
- [mpm] Don't die on errors.

## [`1.1.0` (2016-07-07)](https://github.com/kdeldycke/meta-package-manager/compare/v1.0.0...v1.1.0)

- [pip] Add support for Python's `pip`.

## [`1.0.0` (2016-07-05)](https://github.com/kdeldycke/meta-package-manager/commit/170ce9)

- [mpm] Initial public release.
- [brew,cask] Add support for Homebrew and Cask.
