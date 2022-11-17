# Configuration

All `mpm` options can be set with a configuration file.

## Location

Location depends on OS (see
[`click-extra` doc](https://kdeldycke.github.io/click-extra/config.html#pattern-matching)):

- macOS:
  `~/Library/Application Support/mpm/*.{toml,yaml,yml,json,ini,xml}`
- Unix:
  `~/.config/mpm/*.{toml,yaml,yml,json,ini,xml}`
- Windows (roaming):
  `C:\Users\<user>\AppData\Roaming\mpm\*.{toml,yaml,yml,json,ini,xml}`

## TOML sample

```toml
# My default configuration file.

[mpm]
verbosity = "DEBUG"
manager = ["brew", "cask"]

[mpm.search]
exact = true
```

## Ignore a manager

A user [was looking](https://github.com/matryer/xbar/issues/777) to
always have it ignore `pip` to speed-up execution. That can be solved with the
following config file:

```toml
[mpm]
exclude = [ "pip",]
```

## Overlapping managers

MPM has support for some overlapping package managers. Take for instance `pacman` and its collection of AUR helpers like `paru` and `yay`. All of the alternative helpers have the same source of packages as `pacman` (except if someone added other repositories to them). So updates to a single package may show up multiple times, because AUR helpers depends on `pacman` (which is always installed on the system).

You can fine-tune this behaviour by simply excluding redundant managers depending on your preferrences.

For instance, if `yay` is your preferred helper and `pacman` is polluting your entries, you can setup a configuration file in `~/.config/mpm/config.toml` to exclude the other AUR helpers by default:

```toml
[mpm]
exclude = [ "pacman", "paru",]
```

## Troubleshooting

You can easely debug the way `mpm` source its configuration with the `--show-params`:

```shell-session
$ mpm --show-params
╭───────────────────────────────────┬────────────────────────────┬──────┬─────────────────────────┬──────────────────────────────────────────────┬──────────────────────────────────────────────┬─────────────╮
│ Parameter                         │ ID                         │ Type │ Env. var.               │ Default                                      │ Value                                        │ Source      │
├───────────────────────────────────┼────────────────────────────┼──────┼─────────────────────────┼──────────────────────────────────────────────┼──────────────────────────────────────────────┼─────────────┤
│ <Option all_managers>             │ mpm.all_managers           │ bool │ MPM_ALL_MANAGERS        │ False                                        │ False                                        │ DEFAULT     │
│ <Option apm>                      │ mpm.apm                    │ bool │ MPM_APM                 │ False                                        │ False                                        │ DEFAULT     │
│ <Option apt>                      │ mpm.apt                    │ bool │ MPM_APT                 │ False                                        │ False                                        │ DEFAULT     │
│ <Option apt_mint>                 │ mpm.apt_mint               │ bool │ MPM_APT_MINT            │ False                                        │ False                                        │ DEFAULT     │
│ <Option bar_plugin_path>          │ mpm.bar_plugin_path        │ bool │ MPM_BAR_PLUGIN_PATH     │ False                                        │ False                                        │ DEFAULT     │
│ <Option brew>                     │ mpm.brew                   │ bool │ MPM_BREW                │ False                                        │ False                                        │ DEFAULT     │
│ <Option cargo>                    │ mpm.cargo                  │ bool │ MPM_CARGO               │ False                                        │ False                                        │ DEFAULT     │
│ <Option cask>                     │ mpm.cask                   │ bool │ MPM_CASK                │ False                                        │ False                                        │ DEFAULT     │
│ <Option choco>                    │ mpm.choco                  │ bool │ MPM_CHOCO               │ False                                        │ False                                        │ DEFAULT     │
│ <ColorOption color>               │ mpm.color                  │ bool │ MPM_COLOR               │ True                                         │ True                                         │ DEFAULT     │
│ <Option composer>                 │ mpm.composer               │ bool │ MPM_COMPOSER            │ False                                        │ False                                        │ DEFAULT     │
│ <ConfigOption config>             │ mpm.config                 │ str  │ MPM_CONFIG              │ ~/.config/mpm/*.{toml,yaml,yml,json,ini,xml} │ ~/.config/mpm/*.{toml,yaml,yml,json,ini,xml} │ DEFAULT     │
│ <Option description>              │ mpm.description            │ bool │ MPM_DESCRIPTION         │ False                                        │ False                                        │ DEFAULT     │
│ <Option dnf>                      │ mpm.dnf                    │ bool │ MPM_DNF                 │ False                                        │ False                                        │ DEFAULT     │
│ <Option dry_run>                  │ mpm.dry_run                │ bool │ MPM_DRY_RUN             │ False                                        │ False                                        │ DEFAULT     │
│ <Option emerge>                   │ mpm.emerge                 │ bool │ MPM_EMERGE              │ False                                        │ False                                        │ DEFAULT     │
│ <Option exclude>                  │ mpm.exclude                │ list │ MPM_EXCLUDE             │                                              │                                              │ DEFAULT     │
│ <Option flatpak>                  │ mpm.flatpak                │ bool │ MPM_FLATPAK             │ False                                        │ False                                        │ DEFAULT     │
│ <Option gem>                      │ mpm.gem                    │ bool │ MPM_GEM                 │ False                                        │ False                                        │ DEFAULT     │
│ <HelpOption help>                 │ mpm.help                   │ bool │ MPM_HELP                │ False                                        │ False                                        │ DEFAULT     │
│ <Option ignore_auto_updates>      │ mpm.ignore_auto_updates    │ bool │ MPM_IGNORE_AUTO_UPDATES │ True                                         │ True                                         │ DEFAULT     │
│ <Option manager>                  │ mpm.manager                │ list │ MPM_MANAGER             │                                              │                                              │ DEFAULT     │
│ <Option mas>                      │ mpm.mas                    │ bool │ MPM_MAS                 │ False                                        │ False                                        │ DEFAULT     │
│ <Option npm>                      │ mpm.npm                    │ bool │ MPM_NPM                 │ False                                        │ False                                        │ DEFAULT     │
│ <Option opkg>                     │ mpm.opkg                   │ bool │ MPM_OPKG                │ False                                        │ False                                        │ DEFAULT     │
│ <TableFormatOption output_format> │ mpm.output_format          │ str  │ MPM_OUTPUT_FORMAT       │ rounded_outline                              │ rounded_outline                              │ DEFAULT     │
│ <Option pacman>                   │ mpm.pacman                 │ bool │ MPM_PACMAN              │ False                                        │ False                                        │ DEFAULT     │
│ <Option paru>                     │ mpm.paru                   │ bool │ MPM_PARU                │ False                                        │ False                                        │ DEFAULT     │
│ <Option pip>                      │ mpm.pip                    │ bool │ MPM_PIP                 │ False                                        │ False                                        │ DEFAULT     │
│ <Option pipx>                     │ mpm.pipx                   │ bool │ MPM_PIPX                │ False                                        │ False                                        │ DEFAULT     │
│ <Option scoop>                    │ mpm.scoop                  │ bool │ MPM_SCOOP               │ False                                        │ False                                        │ DEFAULT     │
│ <ShowParamsOption show_params>    │ mpm.show_params            │ bool │ MPM_SHOW_PARAMS         │ False                                        │ True                                         │ COMMANDLINE │
│ <Option snap>                     │ mpm.snap                   │ bool │ MPM_SNAP                │ False                                        │ False                                        │ DEFAULT     │
│ <Option sort_by>                  │ mpm.sort_by                │ str  │ MPM_SORT_BY             │ manager_id                                   │ manager_id                                   │ DEFAULT     │
│ <Option stats>                    │ mpm.stats                  │ bool │ MPM_STATS               │ True                                         │ True                                         │ DEFAULT     │
│ <Option steamcmd>                 │ mpm.steamcmd               │ bool │ MPM_STEAMCMD            │ False                                        │ False                                        │ DEFAULT     │
│ <Option stop_on_error>            │ mpm.stop_on_error          │ bool │ MPM_STOP_ON_ERROR       │ False                                        │ False                                        │ DEFAULT     │
│ <TimerOption time>                │ mpm.time                   │ bool │ MPM_TIME                │ False                                        │ False                                        │ DEFAULT     │
│ <VerbosityOption verbosity>       │ mpm.verbosity              │ str  │ MPM_VERBOSITY           │ INFO                                         │ INFO                                         │ DEFAULT     │
│ <VersionOption version>           │ mpm.version                │ bool │ MPM_VERSION             │ False                                        │ False                                        │ DEFAULT     │
│ <Option vscode>                   │ mpm.vscode                 │ bool │ MPM_VSCODE              │ False                                        │ False                                        │ DEFAULT     │
│ <Option xkcd>                     │ mpm.xkcd                   │ bool │ MPM_XKCD                │ False                                        │ False                                        │ DEFAULT     │
│ <Option yarn>                     │ mpm.yarn                   │ bool │ MPM_YARN                │ False                                        │ False                                        │ DEFAULT     │
│ <Option yay>                      │ mpm.yay                    │ bool │ MPM_YAY                 │ False                                        │ False                                        │ DEFAULT     │
│ <Option yum>                      │ mpm.yum                    │ bool │ MPM_YUM                 │ False                                        │ False                                        │ DEFAULT     │
│ <Option zypper>                   │ mpm.zypper                 │ bool │ MPM_ZYPPER              │ False                                        │ False                                        │ DEFAULT     │
│ <Option merge>                    │ mpm.backup.merge           │ bool │ MPM_MERGE               │ False                                        │ False                                        │ DEFAULT     │
│ <Option overwrite>                │ mpm.backup.overwrite       │ bool │ MPM_OVERWRITE           │ False                                        │ False                                        │ DEFAULT     │
│ <Argument toml_path>              │ mpm.backup.toml_path       │ str  │                         │ -                                            │ -                                            │ DEFAULT     │
│ <Option update_version>           │ mpm.backup.update_version  │ bool │ MPM_UPDATE_VERSION      │ False                                        │ False                                        │ DEFAULT     │
│ <Argument packages_specs>         │ mpm.install.packages_specs │ list │                         │                                              │                                              │ DEFAULT     │
│ <Option duplicates>               │ mpm.installed.duplicates   │ bool │ MPM_DUPLICATES          │ False                                        │ False                                        │ DEFAULT     │
│ <Option plugin_output>            │ mpm.outdated.plugin_output │ bool │ MPM_PLUGIN_OUTPUT       │ False                                        │ False                                        │ DEFAULT     │
│ <Argument packages_specs>         │ mpm.remove.packages_specs  │ list │                         │                                              │                                              │ DEFAULT     │
│ <Argument toml_files>             │ mpm.restore.toml_files     │ list │                         │                                              │                                              │ DEFAULT     │
│ <Option exact>                    │ mpm.search.exact           │ bool │ MPM_EXACT               │ False                                        │ False                                        │ DEFAULT     │
│ <Option extended>                 │ mpm.search.extended        │ bool │ MPM_EXTENDED            │ False                                        │ False                                        │ DEFAULT     │
│ <Argument query>                  │ mpm.search.query           │ str  │                         │                                              │                                              │ DEFAULT     │
│ <Option refilter>                 │ mpm.search.refilter        │ bool │ MPM_REFILTER            │ True                                         │ True                                         │ DEFAULT     │
│ <Option all>                      │ mpm.upgrade.all            │ bool │ MPM_ALL                 │ False                                        │ False                                        │ DEFAULT     │
│ <Argument packages_specs>         │ mpm.upgrade.packages_specs │ list │                         │                                              │                                              │ DEFAULT     │
╰───────────────────────────────────┴────────────────────────────┴──────┴─────────────────────────┴──────────────────────────────────────────────┴──────────────────────────────────────────────┴─────────────╯
```
