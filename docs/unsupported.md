# {octicon}`circle-slash` Unsupported managers

`mpm` wraps [a long list of package managers](managers.md), but not everything that installs software.

Every tool that installs software belongs in one of exactly two places: the [supported list](managers.md), or this page. There is no third state, and absence from both is a gap to be closed rather than a verdict of its own. The goal is total coverage: if it installs software and anyone has heard of it, `mpm` either wraps it or records here why it does not. A blank cell in the [benchmark](benchmark.md) is therefore a to-do, not an answer.

That is a deliberate change of policy. Curating which tools were worth an opinion left readers unable to tell "we looked and declined" apart from "nobody looked", which are very different answers to the only question this page exists to settle.

Two reasons put a tool in the sections below, and the section title carries the verdict:

- ☠️ Its upstream is dead.
- ❌ Or it lacks critical features required by `mpm`.

A third marker rides alongside either of them:

- 🛟 [`topgrade`](managers/topgrade.md) reaches it anyway, so `mpm upgrade --topgrade` still upgrades it. `mpm` wraps `topgrade` as the catch-all for tools too thin to earn a manager of their own, which is why most of this page is still upgradable without being wrapped.

One section per tool, except where several share a verdict word for word: those are grouped under the family they belong to, which names its members up front. Each section is an anchor, so a decision can be cited from anywhere in the documentation, the code or an issue: `https://mpm.run/unsupported/#paq`.

```{hint}
None of these verdicts are permanent. If a tool here looks misjudged, make the case in a [new manager request](https://github.com/kdeldycke/meta-package-manager/issues/new?template=new-package-manager.yml) and the entry will be reassessed.
```

## [`antibody`](https://github.com/getantibody/antibody) ☠️ 🛟

Zsh plugin manager, archived on 2022-05-27 and superseded by [`antidote`](managers/antidote.md), which `mpm` wraps.

## [`antigravity`](https://antigravity.google) ❌ 🛟

Google ships two separate products under the name: the Antigravity **IDE**, a VS Code fork that `topgrade` drives with `--update-extensions`, and the Antigravity **CLI** (`agy`), whose [plugin subcommands](https://antigravity.google/docs/cli/plugins) manage an unrelated set. The IDE's extension flags are documented nowhere, so the row `topgrade` covers has no contract to build on. The `agy plugin list`/`install`/`uninstall` surface is a different tool and would be its own candidate.

## [`app-man`](https://github.com/ivan-hc/AppMan) ❌ 🛟

The same AppImage manager as [`am`](managers/am.md), which `mpm` wraps, under a second name. Its repository carries no implementation at all, only a stub that replaces its own contents with AM's and re-executes it: "*Since version 5, "AppMan" and "AM" have been meged to share the same code*". The script then reads the path it was invoked through to decide whether to install system-wide or under the user's home, which is the entire difference between the two. Wrapping it would also double-count, since `am -fi` already lists AppMan's applications in a table of their own.

## [`apt-rpm`](https://en.wikipedia.org/wiki/APT-RPM) ☠️

APT ported onto RPM, and its last release is `0.5.15lorg3.2` from 2006-06-22. Its original maintainer had stepped away a year before that, announcing in March 2005 "that he would not continue developing it and that he would instead focus on Smart Package Manager, which was planned as a successor to APT-RPM". That successor is on this page too, as [`smart`](#smart), and it is retired as well.

## [`auto-cpufreq`](https://github.com/AdnanHodzic/auto-cpufreq) ❌ 🛟

A CPU speed and power optimizer for Linux, running as a daemon that switches governors and turbo boost according to load and battery state. `topgrade` updates it in place, which is what puts it in the benchmark, but it installs nothing and owns nothing installable: what it manages is a kernel tuning policy, which has no name, no version and no catalog to draw from.

## [`autopackage`](https://en.wikipedia.org/wiki/Autopackage) ☠️

Cross-distribution installer for Linux binaries, and there is nothing left to drive. Its last stable release is `1.4.2` from 2009-05-24, and in August 2010 "Listaller and Autopackage announced that the projects will merge", a successor that no longer ships either. Its own site survives through the Wayback Machine alone.

## [`bash-it`](https://bash-it.readthedocs.io) ❌ 🛟

Bash configuration framework shipping no registry of its own: its plugins, aliases and completions all live inside the single git checkout under `plugins/available`, `aliases/available` and `completion/available`, so `bash-it enable plugin git` only symlinks a file the clone already put on disk and `bash-it disable` removes that symlink again. Nothing is fetched and nothing carries a version of its own: `bash-it update` runs `git fetch` and checks out a tag or `master` across the whole tree, a mechanism its maintainer describes as "*we assume we cloned the project, and we run `git fetch` and things like that*" ([Bash-it/bash-it#1819](https://github.com/Bash-it/bash-it/issues/1819)).

## [`basher`](https://github.com/basherpm/basher) ❌

Package manager for shell scripts, and on the verbs alone the most complete candidate on this page: `list`, `outdated`, `upgrade`, `install` and `uninstall` are all native, so even the staleness read would have needed no synthesis.

It reports no version by any route, which is what settles it. None of the eleven commands it exposes is a `version`, no version constant appears anywhere in its source, and upstream publishes neither tags nor releases, so nothing on disk or in the repository names one. That is [`zgenom`](#zgenom)'s verdict exactly. Nothing on its tracker asks for a version either, so this rests on the observed behaviour rather than on an upstream position, and a release scheme would reopen it.

## [`bpm`](https://github.com/bpm-rocks/bpm) ☠️

Bash package manager, abandoned: 28 commits in all and nothing since 2021-07-25. Little would have been left to wrap in any case, its whole verb surface being `install` and `run`, with no listing, no removal and no upgrade, and its readme conceding it carries no versioning at all, which it blames on Bash having no namespacing.

## [`canopy`](https://docs.enthought.com/canopy/) ☠️

Enthought's scientific Python distribution and the package manager inside it. Its newest release note is "Release notes for Canopy 2.1.9 (23 April 2018)", and the documentation index publishes nothing past that `2.1` line. Eight years without a release is well past the silence the stability policy reads as abandonment.

## [`certbot`](https://certbot.eff.org) ❌ 🛟

The EFF's ACME client, obtaining and renewing TLS certificates. `topgrade` runs `certbot renew` beside its package steps, which is what lands it in this table, but a certificate is not a package: it is issued against a domain the host proves it controls, expires on a schedule of its own, and comes from no catalog anyone can enumerate. Nothing here can be listed, searched, installed by name or removed.

## [`cinnamon-spices`](https://cinnamon-spices.linuxmint.com) ❌ 🛟

What [`topgrade`](managers/topgrade.md) drives here is `cinnamon-spice-updater --update-all`, and that script's own `argparse` block is the whole surface: `--update-all`, `--update <spice-type>`, `--list-simple <spice-type>` and `--list-json <spice-type>`, where a spice-type is one of `applet`, `desklet`, `extension` or `theme`.

Nothing there is a package operation. There is no install and no removal, both of which happen in Cinnamon's own settings UI. The two listings are not an inventory either: `--list-simple` is documented as a "*Simple list of UUIDs (or theme names) with available updates*" and both call `get_updates_of_type`, so they report what is *stale* rather than what is present, which leaves `mpm` no way to enumerate the machine. And the one mutating option takes a *type*, never a spice, so no individual applet can be updated by name. No `--version` is declared either, which disqualifies it a second time over. The [`zr`](#zr) reading.

## [`component`](https://github.com/componentjs/component) ☠️

Front-end package manager and build tool for modular web applications, archived on GitHub with a last push of 2017-12-16. It installed into the working tree rather than onto the machine, so it would have landed among the project-scoped ecosystems below even while alive.

## Container runtimes ❌ 🛟

[`colima`](https://colima.run), [`containers`](https://github.com/containers/podman), [`distrobox`](https://distrobox.it), [`podman`](https://podman.io) and [`toolbx`](https://containertoolbx.org).

Manage container images and running containers, not packages. An image is a filesystem bundle addressed by tag or digest rather than a versioned package, and pulling a newer tag is not an upgrade `mpm` can reason about.

## [`cursor`](https://cursor.com) ❌ 🛟

A VS Code fork that did not inherit the CLI intact: `--list-extensions` launches the Cursor window instead of listing anything ([forum.cursor.com](https://forum.cursor.com/t/command-line-list-extensions/103565), where a moderator grants "*this is not expected behavior*" and the thread closes with no fix). Silently opening a GUI where a listing was asked for is worse than an error, since nothing signals the failure. Cursor's own [CLI documentation](https://cursor.com/docs/cli/installation) covers the separate [`cursor-agent`](#self-updating-applications) binary and never documents the extension flags at all, so there is no contract to build on. Contrast [`vscode`](managers/vscode.md), whose `--list-extensions --show-versions` is documented and stable.

## [`cydia`](https://en.wikipedia.org/wiki/Cydia) ☠️

Package front-end for jailbroken iOS, described by Wikipedia as "a graphical user interface of APT for iOS". Its last release is `1.1.36` from 2020-06-24 and its store closed on 2018-12-16. Dormancy is not the only objection: the APT it drives runs on a phone rather than on the host, which is the scope that declined [`fdroidcl`](#fdroidcl).

## [`declaro`](https://github.com/mantinhas/declaro) ❌

Snapshots one already-installed manager at a time into an editable package list. No unique registry, no license, and its own multi-manager request has sat unaddressed since December 2025 ([mantinhas/declaro#31](https://github.com/mantinhas/declaro/issues/31)).

## [`decman`](https://github.com/kiviktnm/decman) ❌

Arch declarative system manager with no operation verbs at all, flags only: every run reconciles the whole declared state. Its packages come from pacman and its own in-house AUR builder, both already `mpm` territory. Also manages dotfiles, systemd units, users and PGP keys, outside the system scope every `mpm` manager holds to.

## [`dein`](https://github.com/Shougo/dein.vim) ☠️ 🛟

Vim and Neovim plugin manager whose development stopped, superseded by [`dpp`](#dpp), last commit on 2025-09-13. Pure Vimscript, so it also exposes neither a binary to run nor a version to report.

## Dotfiles and repository syncers ❌ 🛟

[`chezmoi`](https://www.chezmoi.io), [`falconf`](https://github.com/GideonBear/falconf), [`git`](https://git-scm.com), [`myrepos`](https://myrepos.branchable.com), [`rcm`](https://github.com/thoughtbot/rcm) and [`yadm`](https://yadm.io).

Synchronize files and Git checkouts, not packages. There is no registry, no package identity and no version: what they track is the user's own content, which is outside the system scope every `mpm` manager holds to.

## [`dpp`](https://github.com/Shougo/dpp.vim) ❌

Vim and Neovim plugin manager, the live successor to [`dein`](#dein), but drivable only from inside the editor: its work happens in a Deno process ([denops.vim](https://github.com/vim-denops/denops.vim)) that Vim starts, and it documents no headless entry point. It reports no version and ships no binary of its own either, so it fails the same two requirements `dein` does, with nothing left to key the manager on.

## [`entropy`](https://github.com/Sabayon/entropy) ☠️

Sabayon Linux's own binary package manager, last pushed 2020-09-07. Six years of silence is twice the span the stability policy reads as abandonment, and no fork has picked it up.

## [`etc-update`](https://wiki.gentoo.org/wiki/Etc-update) ❌ 🛟

Merges pending `/etc` configuration files left behind by a Portage upgrade. It resolves conflicts, installs nothing, and is already covered by [`emerge`](managers/emerge.md), which `mpm` wraps.

## [`fdroidcl`](https://github.com/mvdan/fdroidcl) ❌

Everything but the target reads like a candidate. The F-Droid repository is a real registry nothing else in the pool reaches, `fdroidcl version` answers `v0.8.1`, and `update`, `search`, `scan`, `install` and `uninstall` are all native. Scope is the whole of the objection, and it is [`helm`](#helm)'s objection pointed at a different remote.

fdroidcl installs nothing onto the machine: it drives another computer's package manager over adb. `scan` shells out to `pm list packages` on each connected device, and `install` pushes an APK to one. The two do not even agree on their target. `scan` iterates over every device plugged in, while `install` calls `oneDevice()` and fails unless `ANDROID_SERIAL` or a single connection settles which one. So the inventory describes a set of guest machines, changes with what is attached, and is empty where nothing is, none of which the system scope every `mpm` manager holds to can express. The line is not that attached hardware is out of bounds, since [`fwupd`](managers/fwupd.md) is wrapped and treats each updatable device as a package: its firmware belongs to this machine's own stack, where an Android phone is a separate computer running its own operating system and its own package manager.

## [`fish-plug`](https://github.com/kidonng/plug.fish) ❌ 🛟

Fish plugin manager owning no verb that names a plugin, which its own source settles rather than any behaviour that has to be run: the whole tool is three files and, as its readme puts it, "*< 100 lines of code you can actually read and understand*". Plugins are whatever the `$plugins` variable lists in the user's `config.fish`, and installation is a side effect of starting a shell, `conf.d/plugin_load.fish` cloning any entry whose directory is missing. `functions/plugin_update.fish` takes no argument and pulls every entry of that same list; `functions/plugin_uninstall.fish` takes none either, sweeping the directories the list no longer names and asking `"$plugin_name is disabled, uninstall? (y/N)"` for each, so removal cannot be driven with nobody at the keyboard. There is no listing.

It reports no version either, by any route: upstream publishes zero tags and zero releases, carries no version constant, and its documented install clones a branch, so nothing on disk names one. That is [`zgenom`](#zgenom)'s verdict, reached independently. The project renamed itself to `plug.fish` and rewrote at `v3`, which is the version driven here.

## [`fpm`](https://github.com/jordansissel/fpm) ❌

Builds packages instead of managing them, which leaves nothing for `mpm` to address. It converts a directory, a gem or a Python distribution into a `.deb`, an `.rpm` or a `.pkg` for some other manager to install, so it owns no inventory, installs nothing on its own and removes nothing. The managers that consume what it produces are wrapped already. Alive and busy, pushed 2026-08-26.

## [`fresh`](https://freshshell.com) ❌

Describes itself as "*Bundler for your dot files*": it sources shell configuration (aliases, functions, snippets) out of other people's Git repositories and splices it into the user's own config, then symlinks the result. That is the verdict [`chezmoi`](#dotfiles-and-repository-syncers) and its peers already carry, and it earns a section of its own only because `topgrade` does not reach it, so it cannot sit under a title promising that fallback. Its `search` queries a community wiki rather than a registry, nothing it tracks carries a version of its own, and what it manages is the user's content, outside the system scope every `mpm` manager holds to.

## [`fundle`](https://github.com/danhper/fundle) ☠️ 🛟

Fish plugin manager with no commit since 2023-01-05.

## [`gearlever`](https://gearlever.mijorus.it) ❌ 🛟

Painfully close, and it fails on the version alone. Gear Lever manages the AppImages on a machine and its command line is better shaped than most of this page: `list-installed` enumerates the integrated apps, `list-updates` reports the stale ones, both take a `--json` flag emitting a document with a `schema_version` and per-app `current_version` and `available_version` fields, and `remove`, `update` and `integrate` all act on one app.

None of that is reachable, because nothing reports Gear Lever's own version. Its `Cli.options` table declares `integrate`, `update`, `remove`, `remove-all`, `list-installed`, `list-updates`, `list-update-managers`, `set-update-url`, `set-update-source` and a background fetch, and no version among them. The failure mode is the aggravating part: `Cli.from_options` returns `-1` for an option it does not know, after which `main()` falls through to `GearleverApplication(...).run(sys.argv)`, so a version probe does not fail, it launches the GTK window. That is [`cursor`](#cursor)'s verdict, where opening a GUI in place of an answer is worse than an error because nothing signals it, layered on [`zgenom`](#zgenom)'s. A `--version` upstream would reopen this immediately.

## [`go-global-update`](https://github.com/Gelio/go-global-update) ❌ 🛟

Updates the binaries `go install` put on the machine, and that is the whole of it. A bare run upgrades every one, naming binaries upgrades those, and `--dry-run` simulates the same thing; there is no listing, no install and no removal anywhere in its surface. That leaves an upgrade as its only honest operation, which is the [`zr`](#zr) reading, and [`topgrade`](managers/topgrade.md) already reaches it inside the same `Go` step that runs [`gup`](managers/gup.md). Every binary it touches is one `gup` lists, reports stale, removes and upgrades one at a time, so wrapping it would add a second route to a subset of what `gup` already does. Alive but slowing, last pushed 2024-09-13.

## [`gofish`](https://github.com/fishworks/gofish) ☠️

Cross-platform package manager modelled on Homebrew, down to a registry of its own: "fish food" recipes hosted at [fishworks/fish-food](https://github.com/fishworks/fish-food). Its readme announces the end in as many words, "*THIS PROJECT IS BEING ARCHIVED*", blaming "*the amount of time and money required to maintain this side project*", and no commit has landed since 2022-03-08. The repository is archived and names no successor.

## [`gopm`](https://github.com/gpmgo/gopm) ☠️

Go package manager and build tool, archived on GitHub with a last push of 2019-07-29. Go modules absorbed the job, and the toolchain that resolves them is wrapped as [`go`](managers/go.md).

## [`helix`](https://helix-editor.com) ❌ 🛟

Editor whose whole package-adjacent surface is one flag, `-g, --grammar {fetch|build}`, and it takes no package argument: both modes act on every tree-sitter grammar listed in `languages.toml` at once, so there is no install, remove or upgrade of a single grammar to declare. Nothing reports an inventory either. `hx --health languages` prints a capability matrix over the languages helix ships configuration for, three hundred rows of ✓ and ✘ across the language server, debug adapter, formatter, highlight, textobject and indent columns, truncated to the terminal width and carrying no version anywhere; it answers what helix knows about rather than what the host holds. The grammars are not a registry of helix's own, each being a git repository pinned by revision in that same configuration file. That leaves an all-or-nothing refresh as the only real operation, which is exactly what [`topgrade`](managers/topgrade.md) already runs, so `mpm upgrade --topgrade` reaches it without `mpm` learning the editor. The [`zr`](#zr) reading. Checked against helix `25.07.1`.

## [`helm`](https://helm.sh) ❌ 🛟

Everything about Helm reads like a candidate: chart repositories that are real registries, and `list`, `search`, `install`, `upgrade` and `uninstall` all native. Scope is the whole of the objection, and it is decisive.

Helm does not install onto the machine. Installing a chart "*creates a new release object*" inside a Kubernetes cluster, and `helm list` enumerates the releases of whichever cluster the current context points at. That inventory therefore describes a cluster rather than a host, changes with `kubectl config use-context`, and is empty or unreachable where no cluster is configured at all, none of which the system scope every `mpm` manager holds to can express.

The line is not that Kubernetes is out of bounds: [`krew`](managers/krew.md) is wrapped, and installs `kubectl` plugins as binaries under the user's own home. The object is what differs, a local binary against a remote deployment.

## [`home-manager`](https://github.com/nix-community/home-manager) ❌ 🛟

Draws its packages from nixpkgs, the registry `mpm` already reaches through [`nix`](managers/nix.md): the manual states that "*Nixpkgs packages can be installed to the user profile using `home.packages`*", an option typed `list of package`. No per-package verb either, its command dispatch accepting only whole-state operations like `build`, `switch` and `generations`, so a package is added by editing `home.nix` and running `home-manager switch`. It does report what it installed, through `home-manager packages`, but that inventory is a view onto the same profile `mpm` already reads.

## [`install-release`](https://github.com/Rishang/install-release) ❌ 🛟

Installer of single-binary tools from GitHub and GitLab releases, reporting no version of its own, which is the requirement {attr}`~meta_package_manager.manager.PackageManager.fresh` enforces: without one the manager is never considered available. Both executables it ships, `ir` and `install-release`, reject `--version`, `-V`, `-v` and a `version` subcommand alike, all four checked against `0.8.4`, and no request for one has ever been filed upstream. The companion-binary route that rescued [`raco`](managers/raco.md) does not apply either, the two executables being one entry point under two names rather than a versioned sibling. Otherwise well shaped, which is worth recording: `ls`, `get`, `rm`, `upgrade` and `hold` would have mapped cleanly. The [`zgenom`](#zgenom) verdict. Its own scope is narrower than its help suggests, too: every invocation on macOS answers "*Package installation is only supported on Linux*" and lists nothing, where the help advertises "*Linux/MacOS*".

## [`jam`](https://github.com/caolan/jam) ☠️

Browser-focused JavaScript package manager built on RequireJS, archived on GitHub with a last push of 2016-10-06.

## JetBrains IDE plugins ❌ 🛟

[`android-studio`](https://developer.android.com/studio), [`jetbrains-aqua`](https://www.jetbrains.com/aqua/), [`jetbrains-clion`](https://www.jetbrains.com/clion/), [`jetbrains-datagrip`](https://www.jetbrains.com/datagrip/), [`jetbrains-dataspell`](https://www.jetbrains.com/dataspell/), [`jetbrains-gateway`](https://www.jetbrains.com/remote-development/gateway/), [`jetbrains-goland`](https://www.jetbrains.com/go/), [`jetbrains-idea`](https://www.jetbrains.com/idea/), [`jetbrains-mps`](https://www.jetbrains.com/mps/), [`jetbrains-phpstorm`](https://www.jetbrains.com/phpstorm/), [`jetbrains-pycharm`](https://www.jetbrains.com/pycharm/), [`jetbrains-rider`](https://www.jetbrains.com/rider/), [`jetbrains-rubymine`](https://www.jetbrains.com/ruby/), [`jetbrains-rustrover`](https://www.jetbrains.com/rust/) and [`jetbrains-webstorm`](https://www.jetbrains.com/webstorm/).

Plugins are driven through an **undocumented** `update` subcommand of the IDE binary (topgrade's own comment: "*The `update` command is undocumented, but tested on all of the below*"), which lists nothing, reports free-form text, and refuses outright while the IDE is open ("*Only one instance of … can be run at a time.*", exit 1). No inventory, no contract, and unusable on the very machines where the IDE is in use. Contrast [`vscode`](managers/vscode.md), whose `--list-extensions` is documented and stable, which is why it is wrapped.

## [`jetbrains-toolbox`](https://www.jetbrains.com/toolbox-app/) ❌ 🛟

JetBrains' IDE installer ships no command-line interface at all: it is a tray application, and the only way to drive it non-interactively is the third-party [`jetbrains-toolbox-updater`](https://github.com/GideonBear/jetbrains-toolbox-updater) crate that pokes at its installation directory. That crate is what [`topgrade`](managers/topgrade.md) depends on, `jetbrains-toolbox-updater = "6.0.0"` in its `Cargo.toml`, which is where this row's lifebuoy comes from. Nothing to execute, nothing to list, no version to report.

## [`jetpack`](https://github.com/3ofcoins/jetpack) ☠️ 🛟

FreeBSD jail runtime, a self-described prototype with no commit since 2018-10-25. Not a package manager to begin with.

## [`kakoune`](https://kakoune.org) ❌ 🛟

Editor shipping no plugin manager of any kind, so there is nothing to wrap. Its whole command-line surface is sessions, filters and user-interface selection: `-e` and `-E` execute a command on client or server startup, `-l` lists sessions, and `-d` runs headless, with no install, list or update flag anywhere among them. Plugins are not packages either, being `*.kak` files the user drops into a directory that the readme describes loading wholesale: "*If the `$XDG_CONFIG_HOME/kak/autoload` directory exists, load every `*.kak` files in it, and load recursively any subdirectory*". Nothing names a source, a version or a registry, so what [`topgrade`](managers/topgrade.md) reaches through this editor is a *third-party* plugin manager running inside a headless session, not Kakoune. The [`helix`](#helix) reading, and the same one that leaves the shell frameworks unwrapped. Checked against Kakoune `2026.05.21`.

## [`macos`](https://www.apple.com/macos/) ❌ 🛟

Apple's `softwareupdate(8)` updates the operating system rather than managing packages, putting it outside `mpm`'s domain along with every other system updater a competitor happens to drive. Nothing about it is inventoriable either: `--list` reports the updates *pending* for the machine, `--history` is a log of those applied through the tool and prints its header alone on a current host, and no verb lists installed components, searches a catalog or removes anything. A macOS update cannot be uninstalled.

## [`mash`](https://mash.pkgx.sh) ❌

Runs scripts instead of installing them, which is [`pkgx`](#pkgx)'s verdict one layer up. mash is a 107-line Bash script over pkgx, and `mash <scriptname> [args...]` is the whole usage its own `--help` prints. The source carries no `install`, `remove`, `list`, `search` or `update` branch: naming a script fetches it from `pkgxdev.github.io/mash/<scriptname>`, marks it executable and runs it. What lands on disk is an ETag-validated HTTP cache under the OS cache directory, revalidated on every run, so nothing accumulates and nothing enumerates it. The catalog behind those names is real, trawled from GitHub into a website, and no verb reaches it.

The version probe is not what fails, and the way it reads is worth naming: the script on `main` answers `mash 0.0.0-dev`, while the release workflow substitutes the tag before publishing. Checked against the released `0.4.0`, which answers with its own version.

## [`maza`](https://github.com/tanrax/maza-ad-blocking) ❌ 🛟

Rewrites the local hosts file from an upstream blocklist. A host list is data, not a package: there is nothing to enumerate, version or uninstall.

## [`metapac`](https://github.com/ripytide/metapac) ❌

Declarative multi-backend package manager delegating to 21 backends `mpm` already wraps directly. No per-package `install`/`remove` verb: removed by design, see [ripytide/metapac#197](https://github.com/ripytide/metapac/issues/197). The successor to the archived [`pacdef`](#pacdef), and actively maintained.

## [`microsoft-office`](https://www.microsoft.com/microsoft-365) ❌ 🛟

Runs Microsoft's own updater for one suite of applications. It has a fixed, single-vendor scope with no catalog to search and no packages to enumerate.

## [`microsoft-store`](https://apps.microsoft.com) ❌ 🛟

Driven through a PowerShell call that triggers the Store's own bulk update. It exposes no per-package command line, so there is nothing to list, install or remove individually. Contrast [`winget`](managers/winget.md), Microsoft's actual package CLI, which `mpm` wraps.

## [`neobundle`](https://github.com/Shougo/neobundle.vim) ☠️ 🛟

Vim plugin manager with no commit since 2018-07-26, superseded by [`dein`](#dein), itself superseded by [`dpp`](#dpp).

## [`ninite`](https://ninite.com) ❌

Installs from a real catalog of Windows applications, so the packages are there, but the free product exposes no command line to reach them with: the whole interface is a web form that generates a bespoke `.exe` bundling the selected apps. That installer takes no package argument, lists nothing and removes nothing, which is the same shape that rules out [`microsoft-store`](#microsoft-store). A command line exists only in Ninite Pro, behind a per-machine monthly subscription with no free tier, so no `mpm` install could exercise it and the destructive install/remove round-trip the test suite runs on every wrapped manager could never be provisioned.

## [`oh-my-bash`](https://ohmybash.nntoan.com) ❌ 🛟

Bash configuration framework with no registry of its own: its plugins and themes are files inside the single git checkout, loaded by name from the `plugins=()` array a user hand-edits into `~/.bashrc` and resolved against `$OSH/plugins/<name>/`, so nothing is independently fetched or versioned and a new plugin arrives only as a pull request against the framework itself ([ohmybash/oh-my-bash#771](https://github.com/ohmybash/oh-my-bash/pull/771)). `upgrade_oh_my_bash` is correspondingly a `git pull --rebase` of that one checkout, which is the whole of what `topgrade` already drives. Nor is there a surface to drive it through: [`lib/cli.bash`](https://github.com/ohmybash/oh-my-bash/blob/master/lib/cli.bash) advertises `plugin`, `theme` and `version` subcommands in its completion table but implements all three as `echo 'Not yet implemented'` stubs, leaving no inventory command and no per-package verb.

## [`oh-my-zsh`](https://ohmyz.sh) ❌ 🛟

Zsh configuration framework with no registry of its own: every plugin ships inside the git checkout, and `omz plugin list` is a directory glob over `$ZSH/plugins` and `$ZSH_CUSTOM/plugins` rather than a query against an index. The verb set confirms it, offering only `disable`, `enable`, `info`, `list` and `load`, where `enable` just rewrites the `plugins=()` array in `~/.zshrc` for a directory already on disk: adding a third-party plugin means hand-creating `$ZSH_CUSTOM/plugins/foobar/foobar.plugin.zsh` yourself ([Customization](https://github.com/ohmyzsh/ohmyzsh/wiki/Customization#adding-a-new-plugin)), and the [External plugins](https://github.com/ohmyzsh/ohmyzsh/wiki/External-plugins) page is a hand-curated list of links, not an index. Nothing versioned to install against either: upstream carries no tags, so `omz version` falls through `git describe --tags HEAD` to the branch name.

## [`oneget`](https://github.com/OneGet/oneget) ❌

Windows package-manager *manager*: PackageManagement brokers transactions out to providers (NuGet, PowerShellGet, Chocolatey) instead of owning packages itself, so everything it reaches through PowerShellGet `mpm` already reaches directly through [`pwsh-gallery`](managers/pwsh-gallery.md). Wrapping it would buy a delegation layer and not one extra package, which is the verdict [`metapac`](#metapac) and [`upt`](#upt) get for the same shape. Its upstream has stopped moving besides: the readme declares the module "*currently not in development*" and "*no longer accepting any pull requests*", naming AnyPackage and PowerShellGet as the successors.

## [`opencsw`](https://www.opencsw.org) ☠️

Community collection of Solaris packages in SysV format. Its own front page has announced nothing since 2022-02-15, "Unbound version 1.15.0 has been pushed to unstable", which is four years of silence on a catalogue whose whole value is how current it is.

## [`openpkg`](https://en.wikipedia.org/wiki/OpenPKG) ☠️

Cross-platform RPM-based packaging for Linux, BSD and Solaris. Its own site no longer serves: `openpkg.org` answers with an expired TLS certificate over HTTPS and HTTP alike, which is why this section links Wikipedia instead. That stub carries nothing newer than "in June 2005 it offered more than 880 freely available packages".

## [`pacapt`](https://github.com/icy/pacapt) ☠️

Cross-manager wrapper retired in 2022. All 19 of the package managers it drove are shipped by `mpm`.

## [`pacdef`](https://github.com/steven-omaha/pacdef) ☠️ 🛟

Arch meta package manager, archived on 2025-08-05, its README pointing to [`metapac`](#metapac) as its successor.

## [`package-control`](https://packagecontrol.io) ❌

Sublime Text's package manager, thoroughly alive and backed by a registry of its own at packagecontrol.io. It is drivable only from inside the editor, though: its readme documents installation as three steps through the `Command Palette`, and no command-line entry point exists to list, install or remove anything with nobody at the keyboard. That is the test [`pckr-nvim`](#pckr-nvim) and [`dpp`](#dpp) fail too. Contrast [`micro`](managers/micro.md), an editor `mpm` does wrap, whose plugin flag is handled before its screen is ever initialised and so prints and exits.

## [`packer-aur`](https://github.com/keenerd/packer) ☠️

Arch AUR helper with no commit since 2016-03-25. Superseded by the same AUR helpers as [`yaourt`](#yaourt); the bare `packer` name belongs to HashiCorp's tool and to [`packer-nvim`](#packer-nvim), hence the suffix.

## [`packer-nvim`](https://github.com/wbthomason/packer.nvim) ☠️ 🛟

Neovim plugin manager whose README has declared it unmaintained since August 2023, pointing at [`lazy`](managers/lazy.md), which `mpm` wraps, and at [`pckr-nvim`](#pckr-nvim).

## [`pakku`](https://github.com/kitsunyan/pakku) ☠️

Pacman wrapper with AUR support, abandoned: its last release is `v0.14` from 2019-12-20 and its last commit 2020-11-12. Nothing is out of reach for want of it either, `mpm` wrapping six live tools over the same ground in [`pacaur`](managers/pacaur.md), [`pamac`](managers/pamac.md), [`paru`](managers/paru.md), [`pikaur`](managers/pikaur.md), [`trizen`](managers/trizen.md) and [`yay`](managers/yay.md).

## [`paq`](https://github.com/savq/paq-nvim) ❌ 🛟

Neovim plugin manager clearing both tests its peers failed: installation has a documented headless recipe closing on paq's own `PaqDoneInstall` autocommand, and `paq-lock.json` sits at a fixed path recording each plugin's name, URL and commit, so an inventory needs no configuration loaded. It reports no version of its own, though. `require("paq")` exposes `clean`, `install`, `list`, `log_clean`, `log_open`, `query`, `setup`, `sync` and `update`, and no version constant appears anywhere in its source; upstream tags releases, but a tag never reaches the checkout a user clones. Nothing on its tracker asks for one.

## [`pathogen`](https://github.com/tpope/vim-pathogen) ☠️

Vim plugin manager with no commit since 2022-08-24. Its whole job, splicing plugin directories into `runtimepath`, became a Vim 8 and Neovim built-in, which is what [`vim-pack`](managers/vim-pack.md) wraps.

## [`pbi`](https://github.com/trueos/trueos) ☠️

PC-BSD's Push Button Installer format and the `pbi_*` tools around it. PC-BSD became TrueOS, whose repository is archived with a last push of 2020-04-22, and FreeBSD's own [`pkg`](managers/pkg.md) is what the platform installs with today.

## [`pckr-nvim`](https://github.com/lewis6991/pckr.nvim) ❌

Successor to [`packer-nvim`](#packer-nvim) and actively developed, but drivable only from inside Neovim, and less so than its predecessor was. packer.nvim documented a headless recipe, `nvim --headless -c 'autocmd User PackerComplete quitall' -c 'PackerSync'`, which closed on the completion event named in it; the rewrite emits no autocommand at all, so an unattended run has nothing to wait on, and its `pckr/cli.lua` is the `:Pckr` Ex-command dispatcher rather than the shell entry point the name suggests. Removal blocks on an `OK to remove? [y/N]` prompt in `pckr/display.lua`. Its lockfile is opt-in, written only by the `:Pckr lock` action, and is a Lua table keyed by remote URL, so it is neither guaranteed to exist nor readable without an evaluator the way [`lazy`](managers/lazy.md)'s JSON one is. A request for a synchronous entry point was closed with a redirect to `config` and dependencies ([lewis6991/pckr.nvim#12](https://github.com/lewis6991/pckr.nvim/issues/12)).

## [`pihole`](https://pi-hole.net) ❌ 🛟

DNS ad blocker that updates its own installation and blocklists. It manages a network service and its data, not packages on the host.

## [`pip-review`](https://github.com/jgonggrijp/pip-review) ❌ 🛟

A convenience layer over [`pip`](managers/pip.md), which `mpm` wraps directly: its [readme](https://github.com/jgonggrijp/pip-review/blob/develop/README.rst) opens by calling it "*a convenience wrapper around `pip`*" that lists updates "*by deferring to `pip list --outdated`*" and installs them "*by deferring to `pip install`*". It owns no registry, no installed-package inventory and no per-package verb: `pip-review` takes no package argument, and its flags only choose how to present the same all-outdated set.

## [`pipupgrade`](https://github.com/achillesrasquinha/pipupgrade) ❌ 🛟

Wraps `pip` and nothing else: it discovers the `pip`, `pip3` and `pip2` executables on `PATH` and shells out to them, resolving every candidate version against PyPI, so its whole inventory is the packages `mpm` already reaches through [`pip`](managers/pip.md). Its readme calls it "*The missing command for `pip`*", and what it adds on top is project-file rewriting of `requirements.txt` and `Pipfile` plus a semver-aware upgrade gate, both outside the system scope every `mpm` manager holds to.

## [`pisi`](https://github.com/pisilinux/pisi) ☠️

Pardus' package manager, left behind by the distribution that created it: "Pardus used to use Pisi, but migrated to APT in 2013". The PisiLinux fork carrying it on was last pushed 2022-03-28, past the silence the stability policy reads as abandonment. Its living descendant is Solus' [`eopkg`](managers/eopkg.md), which `mpm` wraps.

## [`pkg-termux`](https://github.com/termux/termux-tools) ❌

Termux's `pkg` is a dispatcher over two managers `mpm` already wraps, which is [`upt`](#upt)'s verdict reached by a different route. Its script branches on `TERMUX_APP_PACKAGE_MANAGER` and forwards every command: under apt, `install` becomes `apt install`, `list-installed` becomes `apt list --installed`, `uninstall` becomes `apt remove`, `files` becomes `dpkg -L` and `search` becomes `apt search`; under pacman the same commands become `pacman -Sy --needed`, `pacman -Q`, `pacman -Rcns`, `pacman -Ql` and `pacman -Sys`. Nothing it accepts reaches a package [`apt`](managers/apt.md) or [`pacman`](managers/pacman.md) cannot.

What it adds is a mirror selection and a cache refresh in front of some of those calls, `select_mirror` and `update_apt_cache`, which is convenience rather than a registry. That is the line [`nala`](managers/nala.md) sits on the other side of: nala was wrapped for owning its own vocabulary, downloader and rollback history, where `pkg` forwards its argv unchanged.

## [`pkgfile`](https://github.com/falconindy/pkgfile) ❌ 🛟

Answers which package owns a given file by searching the `.files` metadata `repo-add` publishes on [`pacman`](managers/pacman.md) mirrors, scoped to the repositories enabled in `/etc/pacman.conf`. Its [man page](https://man.archlinux.org/man/extra/pkgfile/pkgfile.1.en) documents exactly three operations, `--search`, `--list` and `--update`, none of which installs, removes or reports locally-installed packages. `--update` only refreshes the cached index, and that index is pacman's own repository metadata rather than a registry of its own. The bundled `command-not-found` hook can offer to install a match, but delegates to `sudo pacman -S`.

## [`pkgx`](https://pkgx.sh) ❌

Runs programs instead of installing them, which leaves nothing to declare. Every argument is read as a command to execute, so `pkgx list` answers `Error: CmdNotFound("list")` while `pkgx ls` runs `/bin/ls`: there is no `install`, `remove`, `outdated` or `search` verb anywhere, and the one inventory-shaped flag, `--query`, answers whether a single named program could be run rather than reporting what is present. Upstream frames it the same way, describing pkgx as "a 4 MiB, standalone binary that can *run anything*" and noting that after a run "nothing was installed; your wider system is untouched", then directing installation to its sibling [pkgxdev/pkgm](https://github.com/pkgxdev/pkgm), which "fully installs `pkgx` packages to `/usr/local/`". So the package manager of this lineage is `pkgm`, which carries `install`, `uninstall`, `list`, `outdated` and `update`. Checked against pkgx `2.11.0`.

`tea` is this tool's former name, and the verdict above covers it. GitHub still answers `teaxyz/cli` with [pkgxdev/pkgx](https://github.com/pkgxdev/pkgx), one repository created on 2021-11-20. Its releases carry the rename in their artifact names: `tea-1.0.0-alpha.4` on 2023-09-17, then `pkgx-1.0.0` on 2023-10-02. The `teaxyz` organization now publishes a token protocol and no package manager. `tea.xyz` heads its own page with a [*Looking for the package manager?*](https://pkgx.dev) link.

## [`plug`](https://github.com/junegunn/vim-plug) ❌ 🛟

Vim and Neovim plugin manager, drivable unattended unlike [`dein`](#dein) and [`dpp`](#dpp): `PlugInstall` runs under `--headless` and exits cleanly. It reports no version, though, and by design. It ships as a single file the documented install fetches from `master`, so no release tag ever reaches the copy on disk, and it records no manifest either: the plugin list lives in the user's own config. The request for a version command was closed on the maintainer's ["it doesn't have a version number in it, so it's not currently possible"](https://github.com/junegunn/vim-plug/issues/1266#issuecomment-1983679360).

## [`ppm`](https://en.wikipedia.org/wiki/ActivePerl) ☠️

ActiveState's Perl Package Manager, which ships inside ActivePerl rather than on its own. That distribution's last release is `5.28.1` from 2019-05-30, seven years back, so the manager has had no vehicle since. CPAN itself stays reachable through [`cpan`](managers/cpan.md).

## [`restarts`](https://github.com/liske/needrestart) ❌ 🛟

[`needrestart`](https://github.com/liske/needrestart) restarts services whose libraries were replaced by an upgrade. It installs nothing and owns no packages: it reacts to what a real package manager just did.

## [`rye`](https://rye.astral.sh) ☠️ 🛟

Python project manager, archived by Astral with its last release `0.44.0` dating from 2025-02-26. Its readme states Rye "is no longer developed" and that "no further updates are planned, including security updates", naming [uv](https://docs.astral.sh/uv/) as "the successor project from the same maintainers". `mpm` wraps that successor as [`uv`](managers/uv.md) and [`uvx`](managers/uvx.md), so the global tools and interpreters Rye installed are reached without it.

## [`sage`](https://web.archive.org/web/20191121154506/https://github.com/svnpenn/sage) ☠️

Cygwin package manager, offered as an alternative to [`apt-cyg`](managers/apt-cyg.md), which `mpm` wraps. It is gone in the strongest sense available: `github.com/svnpenn/sage` 404s and so does the `svnpenn` account that owned it, so the project was not renamed or transferred, it was deleted along with its owner. The title above therefore links the Wayback Machine's last capture, from 2019-11-21, there being nothing live left to point at. No fork carries the name.

## Self-updating applications ❌ 🛟

[`atuin`](https://atuin.sh), [`claude-code`](https://claude.com/product/claude-code), [`codex`](https://github.com/openai/codex), [`cursor-agent`](https://cursor.com/cli), [`deno`](https://deno.com), [`flutter`](https://flutter.dev), [`fossil`](https://fossil-scm.org), [`helix-db`](https://helix-db.com), [`opencode`](https://github.com/sst/opencode), [`spicetify`](https://spicetify.app) and [`typst`](https://typst.app).

Update only themselves. There is no catalog, no inventory and no per-package operation to map: the whole surface is one command that replaces the binary in place.

## [`sera`](https://gitlab.com/cscs/sera) ❌ 🛟

Command-line updater for KDE Plasma addons, and the closest this page comes to a candidate that fails on one requirement alone: it does list what is installed, which is the thing most tools here cannot do, and `list_current_packages` even emits each addon as `{"NM": name, "VO": version}`.

What it has no route to is its own version. The script holds one internally, `version="v2.9.9-1"`, but nothing prints it: its whole dispatch is `help`, `list`, `check`, `sync` and `upgrade`, with `*) exit;;` swallowing anything else, so `sera --version` exits silently and a probe reads nothing. Upstream publishes no tags either. That is [`zgenom`](#zgenom)'s verdict, and {attr}`~meta_package_manager.manager.PackageManager.fresh` enforces it. A second obstacle sits behind it: `sync` is dispatched as `upgrade_package "$1" "$2"` and wants a content id *and* an addon name, so one identifier could not drive an upgrade even with a version in hand, which is the [`0install`](managers/zeroinstall.md) shape.

## [`smart`](https://github.com/smartpm/smart) ☠️

No commit since 2016-10-27. An early cross-distribution package manager over the RPM and dpkg archives among others, chasing the same goal as `mpm`; every archive it drove has a manager today.

## [`sparkle`](https://sparkle-project.org) ❌ 🛟

An update framework developers embed in their own macOS applications, described by its site as "*an easy-to-use software update framework for macOS applications*". Each application carries its own appcast feed and Sparkle's helper acts on one bundle path at a time, so there is no catalog and no inventory anywhere in it.

`topgrade` reaches it by supplying the enumeration itself, walking `/Applications`, probing every bundle with `--probe` and updating whichever answer. That is a directory listing performed by the caller, not something Sparkle exposes, and it leaves nothing here to list, search, install by name or remove.

## [`spm`](https://github.com/spmjs/spm) ☠️

Static package manager for front-end assets, archived on GitHub with a last push of 2018-08-15. It shares its abbreviation with Swift's package manager, which is a different tool and project-scoped.

## [`sysget`](https://github.com/cvengler/sysget) ☠️

Cross-manager wrapper retired in 2019. All 21 of the package managers it drove are shipped by `mpm`.

## System database refreshers ❌ 🛟

[`clam-av-db`](https://www.clamav.net), [`lensfun`](https://lensfun.github.io) and [`mandb`](https://man-db.gitlab.io/man-db).

Rebuild a local database from files already on disk. Nothing is fetched, installed or removed, and the database has no package identity to report.

## [`tldr`](https://tldr.sh) ❌ 🛟

Refreshes a local cache of community-written command summaries. The pages are documentation, not packages: nothing is installed, versioned or removable.

## [`tmux`](https://github.com/tmux-plugins/tpm) ❌ 🛟

The Tmux Plugin Manager clears the bar most editor and shell plugin managers fail: it is genuinely scriptable, shipping `bin/install_plugins`, `bin/update_plugins` and `bin/clean_plugins`, and its own comment notes tmux "*does not need to be started in order to run this script*". Nobody has to be at the keyboard.

What it has no shape for is a package. Those three scripts are the whole surface and none takes an argument: the plugin set is whatever `.tmux.conf` declares, so installing is all-or-nothing from that file and there is no verb naming one plugin. Neither is there a listing, nor a version of its own, upstream tagging its repository but publishing no releases and putting nothing on disk that names one.

No inventory, no per-package operation, and `topgrade` already reaching it leaves nothing a wrapper would add, which is [`zr`](#zr)'s verdict.

## `topgrade` internal steps ❌ 🛟

[`remotes`](https://github.com/topgrade-rs/topgrade), [`rtcl`](https://github.com/topgrade-rs/topgrade) and [`system`](https://github.com/topgrade-rs/topgrade).

Not tools: internal steps of [`topgrade`](managers/topgrade.md), which `mpm` already wraps. They name no upstream project of their own and install nothing.

## [`tpack`](https://github.com/tmuxpack/tpack) ❌ 🛟

A Go rewrite of the Tmux Plugin Manager with a terminal interface, and it lands the same way as [`tmux`](#tmux) for the same reason, though not for identical reasons throughout. What it shares is decisive: there is no listing command at all, and neither of its state-changing verbs names a plugin. `tpack install` is documented as *"Install all plugins declared in tmux.conf"* and takes no positional, while `tpack clean` removes *"plugin directories not declared in tmux.conf"*, so the plugin set is the user's configuration file in both directions and nothing installs or removes one plugin. Where it does go further than tpm is `tpack update [plugin...]`, which names plugins, alongside a `check-updates` read; that leaves an upgrade as the entire honest surface a wrapper could offer, which is what [`topgrade`](managers/topgrade.md) already reaches. The [`zr`](#zr) reading. Checked against tpack `1.2.1`.

## [`up2date`](https://en.wikipedia.org/wiki/Up2date) ☠️

Red Hat's RPM updater, retired by its own vendor: "As of Fedora Core 5 and Red Hat Enterprise Linux 5, up2date is no longer shipped with the distribution; yum is used instead." That successor is wrapped as [`yum`](managers/yum.md).

## [`upm`](https://github.com/epitron/upm) ❌

"*Universal Package Manager*", putting one syntax over apk, apt, guix, opkg, pacman, pkg, pkg_add, pkgin, xbps and yum. It owns no registry: every command is translated to whichever of those the host already carries, all of them wrapped by `mpm` directly, so it reaches no package `mpm` cannot. That is [`upt`](#upt)'s verdict word for word, and like `upt` it reads as a peer of `mpm` rather than a candidate to wrap.

## [`upt`](https://github.com/sigoden/upt) ❌

Translates one CLI vocabulary onto whichever single OS-level manager is detected, never more than one per invocation, by the maintainer's own account: "*upt is just aliases, nothing more*" ([sigoden/upt#60](https://github.com/sigoden/upt/issues/60#issuecomment-2560419544)).

## [`vim`](https://www.vim.org) ❌ 🛟

Vim's own package feature loads plugins but never fetches them, which leaves nothing to wrap. Asked directly, Vim `9.2` reports `has('packages')` as `1` and `exists(':packadd')` as `2`, while `:PackUpdate` and `:PackAdd` both come back `0`: the one command it has puts a package already on disk onto the runtime path. Getting it there is the user's job, a plugin being a directory under `pack/*/start/` that they clone or copy themselves, so there is no registry, no listing, and no install, update or removal of anything.

That is precisely what separates it from [`vim-pack`](managers/vim-pack.md), which `mpm` does wrap: Neovim's manager takes sources and records them, where Vim's feature only reads a directory. What [`topgrade`](managers/topgrade.md) drives through this row is third-party managers anyway, its Vim step forcing a vim-plug update or running a `update_plugins.py` the user supplies.

## [`volo`](https://github.com/volojs/volo) ☠️

Front-end project tool that added dependencies by fetching them from GitHub, last pushed 2022-11-25. That is past the roughly three years of silence the stability policy reads as abandonment, and what it created was a project template rather than machine-wide state.

## [`voom`](https://github.com/airblade/voom) ❌ 🛟

Vim plugin manager in a hundred lines of POSIX shell, and the benchmark pointed at the wrong tool until now: its homepage named [VOoM](https://www.vim.org/scripts/script.php?script_id=2657), a two-pane outliner plugin that installs nothing, while what `topgrade` actually drives is a *binary*, its `run_voom` requiring `voom` on the path and running `voom update`.

The tool it does name is declined on the same two grounds as the rest of this family. It reports no version by any route: the script's whole option surface is `help | --help | -h`, it carries no version constant, and upstream publishes zero tags and zero releases, which is [`zgenom`](#zgenom)'s verdict. And no verb names a plugin to install or remove: its own synopsis is "*Run `voom` to install/uninstall; `voom update` to update already-installed plugins*", so the set is the `~/.vim/plugins` manifest and a bare run reconciles the directory to that file in both directions. `update [-q] <name>` does name one plugin, which is exactly as far as [`tpack`](#tpack) gets, and it leaves an upgrade as the whole surface a wrapper could offer.

## [`vundle`](https://github.com/VundleVim/Vundle.vim) ❌ 🛟

Vim plugin manager reporting no version through anything a probe can read, which is what [`PackageManager.fresh`](managers.md) requires: `g:vundle_version` does not exist, checked by asking Vim for it, and the `0.10.2` in `autoload/vundle.vim` is a comment rather than a variable. Upstream tags releases but publishes none, and the documented install clones `master`, so the copy on disk names no version either. The companion-binary route does not help: the binary here is `vim`, whose version is Vim's own, which is the argument that settled [`zigup`](#zigup).

It clears more of the bar than most of this page, which is worth recording. Driven under `vim -es -u <vimrc>`, `PluginInstall tpope/vim-surround` really did install a plugin the configuration never declared, so it reaches packages one at a time, unlike [`tmux`](#tmux) or [`fish-plug`](#fish-plug). What it has no shape for is an inventory: the only listing is the `g:vundle#bundles` list built from the `Plugin` lines of the user's `vimrc`, so it echoes the configuration rather than the machine. After that ad-hoc install it still reported two plugins while three sat on disk. Checked against Vundle `0.10.2` and Vim `9.2`.

## [`waydroid`](https://waydro.id) ❌ 🛟

Runs an Android system in a container. It installs no packages of its own, and what runs inside it is out of reach of the host's package managers.

## [`whohas`](https://github.com/whohas/whohas) ☠️

Cross-distribution search retired in 2015. All 16 of the distribution archives it queried have a manager in `mpm`.

## Windows Subsystem for Linux ❌ 🛟

[`wsl`](https://learn.microsoft.com/windows/wsl/) and [`wsl-update`](https://learn.microsoft.com/windows/wsl/).

Update the WSL kernel and its distributions. WSL is a platform, not a package manager: the managers that run inside a WSL distribution are the ones `mpm` wraps, and it wraps them directly.

## [`windsurf`](https://windsurf.com) ❌ 🛟

A VS Code fork whose vendor documents a launcher (`windsurf .`) and never the extension-management flags, so nothing upstream commits to `--list-extensions` behaving as it does in VS Code. The one fork where the community did test it, [`cursor`](#cursor), found the listing opens the editor window instead. Reassess with a citation the day Windsurf documents the flags or a listing is confirmed working.

## [`wpkg`](https://windowspackager.org) ☠️

Windows Packager, a dpkg clone bringing Debian-style packaging and apt-like verbs to Windows. Its upstream is gone: windowspackager.org now serves a parking page offering the domain for sale, no canonical repository survives it, and the only trace left on GitHub is a single-star fork carrying no releases. Not to be confused with the unrelated [WPKG](https://wpkg.org) deployment tool, which shares the name and nothing else.

## [`yaourt`](https://github.com/archlinuxfr/yaourt) ☠️

Archived, and self-described `[unmaintained]` in its own repository description, with no commit since 2018-12. The dominant AUR helper before `yay`; `mpm` wraps its successors [`yay`](managers/yay.md) and [`paru`](managers/paru.md).

## [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) ❌

A command-line audio and video downloader, not a package manager: what it fetches is media, addressed by URL, carrying no name, no version and no catalog to enumerate. Its `--update` flag replaces its own binary in place, which is the whole of its resemblance to one and the reason it keeps being suggested.

That is the verdict the [self-updating applications](#self-updating-applications) family carries, and yt-dlp would sit there but for the lifebuoy: no competitor drives it, so it cannot share a title promising `topgrade` reaches it.

## [`zgenom`](https://github.com/jandamm/zgenom) ❌ 🛟

Zsh plugin manager reporting no version through any binary: its whole function set runs from `zgenom-api` to `zgenom-update` with no version command anywhere, so the probe that establishes a shell-function manager's presence has nothing to read. The upstream request to tag releases was closed on the maintainer's position that "*I consider everything merged into main as a stable release*" ([jandamm/zgenom#120](https://github.com/jandamm/zgenom/issues/120#issuecomment-1112530002)), so no version is coming. Its `list` compounds that by `cat`-ing the generated `init.zsh` verbatim rather than reporting an inventory.

## [`zigup`](https://github.com/marler8997/zigup) ❌ 🛟

Zig compiler manager reporting no version of its own, which is what disqualifies it: a bare argument means *install this Zig version*, so `--version`, `-V`, `-v` and `version` are each read as a version string and rejected. Upstream confirms the shape rather than the wording of it, having closed a report of the resulting panic by replacing it with `error: invalid zig version 'foo', unable to create a download URL for it` ([marler8997/zigup#187](https://github.com/marler8997/zigup/issues/187)); no request for a version flag was ever filed. Nothing else carries the number either, `build.zig.zon` declaring a `0.0.1` that has never moved while releases are date-stamped, and the companion-binary route that rescued [`raco`](managers/raco.md) does not apply: `zig` is what zigup installs rather than a sibling it ships with, so its version answers for whichever compiler is currently default. The [`zgenom`](#zgenom) verdict, and the rest of the tool is otherwise well shaped: `list`, `fetch`, `clean` and `keep` would have mapped cleanly.

## [`zr`](https://github.com/jedahan/zr) ❌ 🛟

Zsh plugin manager owning no inventory to report: plugins are the arguments you hand it, so its whole `main.rs` recognizes `--update`, `--help`, `--version` and identifiers containing a slash, and there is no state to list. Wrapping it would buy a single `upgrade_all` over `zr --update`, which is what [`topgrade`](managers/topgrade.md) already reaches. No upstream request for a listing exists: the design is deliberate, documented in its README.

## Project-scoped dependency managers

Tools that resolve dependencies inside a working tree are out of scope today.

```{todo}
This is a big feature for the future, but is already delimited by the {attr}`~meta_package_manager.manager.ManagerScope.PROJECT` concept, the {meth}`~meta_package_manager.manager.PackageManager.discover_projects` extension point, and [issue #1725](https://github.com/kdeldycke/meta-package-manager/issues/1725).
```

`mpm` already covers the system-scoped part of these managers:

| Ecosystem             | Project files                                                                        | `mpm` manager                                                                    |
| :-------------------- | :----------------------------------------------------------------------------------- | :------------------------------------------------------------------------------- |
| C/C++                 | `conanfile.txt` (Conan), `vcpkg.json` (vcpkg)                                        | —                                                                                |
| Conda                 | `conda-lock.yml`                                                                     | [`conda`](managers/conda.md)                                                     |
| Go                    | `go.mod`, `go.sum`                                                                   | —                                                                                |
| Haskell               | `stack.yaml` (Stack), `package.yaml` (hpack), `*.cabal`, `cabal.project` (Cabal)     | —                                                                                |
| Java                  | `pom.xml` (Maven), `build.gradle` (Gradle), `ivy.xml`                                | —                                                                                |
| JavaScript            | `package.json`, `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`                   | [`npm`](managers/npm.md), [`yarn`](managers/yarn.md), [`pnpm`](managers/pnpm.md) |
| .NET                  | `*.csproj`, `packages.config` (NuGet)                                                | —                                                                                |
| Perl                  | `cpanfile`                                                                           | [`cpan`](managers/cpan.md)                                                       |
| PHP                   | `composer.json`, `composer.lock`                                                     | [`composer`](managers/composer.md)                                               |
| Python                | `requirements.txt`, `pyproject.toml`, `poetry.lock`, `uv.lock`                       | [`pip`](managers/pip.md), [`uv`](managers/uv.md)                                 |
| Ruby                  | `Gemfile`, `Gemfile.lock`                                                            | [`gem`](managers/gem.md)                                                         |
| Rust                  | `Cargo.toml`, `Cargo.lock`                                                           | [`cargo`](managers/cargo.md)                                                     |
| Swift and Objective-C | `Package.swift`, `Package.resolved` (SwiftPM), `Podfile`, `Podfile.lock` (CocoaPods) | —                                                                                |
