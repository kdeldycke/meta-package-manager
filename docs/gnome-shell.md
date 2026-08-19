# {octicon}`plug` GNOME Shell extension

The Meta Package Manager project maintains a GNOME Shell extension.

A top bar indicator lists the outdated packages reported by `mpm outdated` across every package manager on the system, and lets you upgrade them one by one or per manager. Each outdated package has its version diff colored with the same convention as `mpm outdated`: unchanged prefix in gray, installed-version suffix in red, latest-version suffix in green.

The extension is a frontend to the `mpm` CLI, which must be installed separately: see {doc}`install`. It looks for `mpm` on the session `PATH`, then in well-known locations (`~/.local/bin`, `/usr/local/bin`, Linuxbrew), and a custom launcher (like `uv run mpm`) can be configured in its settings. `mpm` `6.4.0` or newer is required.

## Requirements

- GNOME Shell `46` to `50`.
- The `mpm` CLI, `6.4.0` or newer, reachable from the GNOME session.
- For upgrades run in a terminal: any of `xdg-terminal-exec`, Ptyxis, Console (`kgx`) or GNOME Terminal, or a custom terminal command set in the extension settings.

## Installation

### From extensions.gnome.org

The extension is not yet published on [extensions.gnome.org](https://extensions.gnome.org). Once it lands there, it will be installable with one click from the site. Until then, use one of the methods below.

### From a release zip

Every [GitHub release](https://github.com/kdeldycke/meta-package-manager/releases/latest) carries the packed extension as a `mpm-gnome-shell-extension.zip` asset, next to the `mpm` binaries. Its provenance is attested, so you can verify it was built by this project's release pipeline before installing:

```shell-session
$ gh attestation verify mpm-gnome-shell-extension.zip --repo kdeldycke/meta-package-manager --signer-repo kdeldycke/repomatic
```

Then install it:

```shell-session
$ gnome-extensions install --force mpm-gnome-shell-extension.zip
```

```{important}
A running GNOME Shell does not pick up a freshly installed extension, and `gnome-extensions enable` asks the shell rather than the disk. Run it too early and it answers `Extension "mpm@kdeldycke.github.io" does not exist`, however successful the install was. Restart the session first.
```

A Wayland session cannot restart the shell in place, so end the session and log back in:

```shell-session
$ gnome-session-quit --logout --no-prompt
```

An X11 session can restart the shell alone, from the `Alt`+`F2` prompt: type `r`, then `Enter`.

Once the shell is back, enable the extension:

```shell-session
$ gnome-extensions enable mpm@kdeldycke.github.io
```

`State: ACTIVE` confirms the shell loaded it:

```shell-session
$ gnome-extensions info mpm@kdeldycke.github.io
mpm@kdeldycke.github.io
  Name: Meta Package Manager
  (...)
  Enabled: Yes
  State: ACTIVE
```

Between releases, the bleeding-edge equivalent is produced on each extension change as a workflow artifact of [`tests-gnome-extension.yaml`](https://github.com/kdeldycke/meta-package-manager/actions/workflows/tests-gnome-extension.yaml).

### From a source checkout

```shell-session
$ git clone https://github.com/kdeldycke/meta-package-manager.git
$ cd ./meta-package-manager
$ glib-compile-schemas "gnome-shell/mpm@kdeldycke.github.io/schemas/"
$ ln -snf "$(pwd)/gnome-shell/mpm@kdeldycke.github.io" ~/.local/share/gnome-shell/extensions/
```

Restart the session as above, then enable it:

```shell-session
$ gnome-extensions enable mpm@kdeldycke.github.io
```

## Configuration

Settings live in the extension preferences window, also reachable from the indicator menu:

```{image} assets/gnome-shell-preferences.png
:alt: The preferences window of the GNOME Shell extension
:align: center
:width: 400px
```


| Setting                | Description                                                     | Type    | Default |
| ---------------------- | --------------------------------------------------------------- | ------- | ------- |
| `submenu-layout`       | Group packages into a sub-menu for each manager.                | Boolean | `false` |
| `check-interval`       | Minutes between two package checks.                             | Integer | `420`   |
| `boot-wait`            | Seconds before the first check after login.                     | Integer | `30`    |
| `timeout`              | Seconds passed to `mpm --timeout` for background checks.        | Integer | `60`    |
| `mpm-command`          | Custom `mpm` launcher, empty to autodetect.                     | String  | Empty   |
| `always-visible`       | Show the indicator even when everything is up to date.          | Boolean | `true`  |
| `show-count`           | Show the outdated package count next to the icon.               | Boolean | `true`  |
| `notify`               | Desktop notification when new outdated packages appear.         | Boolean | `false` |
| `upgrade-in-terminal`  | Run upgrades in a terminal window.                              | Boolean | `true`  |
| `terminal-command`     | Custom terminal emulator, empty to autodetect.                  | String  | Empty   |
| `post-upgrade-recheck` | Seconds before refreshing the list after an upgrade is started. | Integer | `300`   |

These settings only drive the menu layout and check cadence. Everything else comes from `mpm`'s own configuration file: the extension passes no option beyond the ones it decides itself, so the file found at its default location on the system applies to every run it triggers. See {doc}`configuration` for the search paths and the full schema.

## Panel icons

The extension ships no state artwork. Each state names a stock symbolic icon, which the shell resolves against whichever icon theme is in force, recolors with the panel foreground, and lets a desktop theme restyle: an Ubuntu desktop draws Yaru's rendering of these names, not Adwaita's.

| State | Adwaita | Yaru | Icon name | Menubar plugin | Shown when |
| :---------------- | :-----: | :--: | :----------------------------------- | :------------- | :------------------------------------------------------ |
| Unknown | <img src="https://raw.githubusercontent.com/StorageB/icons/main/GNOME48Adwaita/neutral/status/content-loading-symbolic.svg" width="18"> | <img src="https://raw.githubusercontent.com/ubuntu/yaru/master/icons/Yaru/scalable/status/content-loading-symbolic.svg" width="18"> | `content-loading-symbolic` | | Before the first check of the session, and during one. |
| Up to date | <img src="https://raw.githubusercontent.com/StorageB/icons/main/GNOME48Adwaita/neutral/actions/selection-mode-symbolic.svg" width="18"> | <img src="https://raw.githubusercontent.com/ubuntu/yaru/master/icons/Yaru/scalable/actions/selection-mode-symbolic.svg" width="18"> | `selection-mode-symbolic` | 📦✓ | No selected manager reports an upgrade. |
| Updates available | <img src="https://raw.githubusercontent.com/StorageB/icons/main/GNOME48Adwaita/neutral/status/software-update-available-symbolic.svg" width="18"> | <img src="https://raw.githubusercontent.com/ubuntu/yaru/master/icons/Yaru/scalable/status/software-update-available-symbolic.svg" width="18"> | `software-update-available-symbolic` | 🎁↑N | Packages can be upgraded. Also marks each *Upgrade all* row. |
| Error | <img src="https://raw.githubusercontent.com/StorageB/icons/main/GNOME48Adwaita/neutral/status/software-update-urgent-symbolic.svg" width="18"> | <img src="https://raw.githubusercontent.com/ubuntu/yaru/master/icons/Yaru/scalable/status/software-update-urgent-symbolic.svg" width="18"> | `software-update-urgent-symbolic` | ⚠️ ❗️ | A check failed, or no runnable `mpm` was found. |
| Manager failed | <img src="https://raw.githubusercontent.com/StorageB/icons/main/GNOME48Adwaita/neutral/status/dialog-warning-symbolic.svg" width="18"> | <img src="https://raw.githubusercontent.com/ubuntu/yaru/master/icons/Yaru/scalable/status/dialog-warning-symbolic.svg" width="18"> | `dialog-warning-symbolic` | ⚠️ | On the sub-menu header of a manager that reported errors. |

The two rendering columns are why the names matter more than any drawing: Yaru defines all five itself, so an Ubuntu desktop never draws the Adwaita ones. Both are shown from their upstream repositories, and neither is bundled here. To browse the rest, the full [Adwaita](https://github.com/StorageB/icons/blob/main/GNOME48Adwaita/icons.md) and [Yaru](https://github.com/StorageB/icons/blob/main/Yaru/icons.md) name-to-preview lists are worth a bookmark, as is the GNOME design team's [Icon Library](https://flathub.org/apps/org.gnome.design.IconLibrary). The preferences window carries the one piece of artwork the extension does ship, the project logo in its *About* row.

## Menu actions

Clicking a package runs `mpm --<manager-id> upgrade <package-id>`, and a section's *Upgrade all* entry runs `mpm --<manager-id> upgrade --all`. Neither invokes the package manager directly, so a click is subject to the same policy as the `mpm` run that rendered the menu: manager selection, {doc}`sudo` escalation, per-manager {doc}`overrides` and the release-age {doc}`cooldown` all apply.

By default the command opens in a terminal window, so the run can be followed and `sudo` can prompt for a password. Turning `upgrade-in-terminal` off runs upgrades silently in the background: system package managers then need passwordless escalation, as `mpm` cannot prompt without a terminal. See the `NOPASSWD` guidance in {doc}`sudo`.

Since a terminal window detaches from the process actually running the upgrade, the extension cannot tell when it completes: it refreshes the package list a few minutes after launching one (`post-upgrade-recheck`), and a *Check now* entry forces a refresh at any time.

When no `mpm` is found on the system, the menu carries a bootstrap pair in place of the package list: *Install mpm with uv* runs `uv tool install --upgrade meta-package-manager` through the same terminal path as an upgrade, and *Open mpm installation instructions* opens {doc}`install` for the systems `uv` does not answer for. The {doc}`menubar plugin <bar-plugin>` offers the same pair.

## Screenshots

Both layouts, photographed from a real GNOME session driven by `docs/gnome_screenshots_update.py` and refreshed by [`docs-screenshots.yaml`](https://github.com/kdeldycke/meta-package-manager/blob/main/.github/workflows/docs-screenshots.yaml) whenever the extension changes.
Each pair follows the appearance of this page, the shell restyling its menu with the desktop's light or dark preference and the version diff keeping its colors legible on both.

The default flat layout lists every manager's packages inline, under a header counting them:

```{image} assets/gnome-shell-flatmenu-light.png
:alt: The extension's menu listing outdated packages inline, one header per package manager
:align: center
:class: only-light
```

```{image} assets/gnome-shell-flatmenu-dark.png
:alt: The extension's menu listing outdated packages inline, one header per package manager
:align: center
:class: only-dark
```

With `submenu-layout` enabled, each manager collapses into a submenu of its own:

```{image} assets/gnome-shell-submenu-light.png
:alt: The extension's menu with one submenu per package manager
:align: center
:class: only-light
```

```{image} assets/gnome-shell-submenu-dark.png
:alt: The extension's menu with one submenu per package manager
:align: center
:class: only-dark
```

## Development workflow

The extension lives in the [`gnome-shell/` directory](https://github.com/kdeldycke/meta-package-manager/tree/main/gnome-shell) of the `mpm` repository and shares its version, release cycle and issue tracker.

Its logic is split in two: `extension.js` owns the widgetry while `mpm.js` is shell-free (it never imports `resource:///org/gnome/shell/*` modules), so the latter runs under a bare `gjs` interpreter:

```shell-session
$ gjs -m tests/gnome/run-tests.js
ok 1 - parseVersion nominal
(...)
```

Static invariants (metadata, GSettings schema, stylesheet and icon drift) are enforced by `tests/test_gnome_extension.py` in the regular Python test suite. The [`tests-gnome-extension.yaml` workflow](https://github.com/kdeldycke/meta-package-manager/actions/workflows/tests-gnome-extension.yaml) runs the gjs suite, checks the sources with [`shexli`](https://pypi.org/project/shexli/) (the static analyzer extensions.gnome.org applies to every upload), packs the installable zip with `gnome-extensions pack`, and proves it installs with a `gnome-extensions install` round-trip.

Its `eslint` job holds the JavaScript to GNOME Shell's own coding style, with the [`eslint-config-gnome`](https://gitlab.gnome.org/World/javascript/eslint-config-gnome) rules declared by `gnome-shell/eslint.config.mjs` and pinned to the commit `gnome-shell` itself pins. No `package.json` or lockfile is committed: nobody would keep one refreshed, so the ESLint stack floats and a 7-day `npm --min-release-age` window gates the whole resolved tree, the same supply-chain guard `mpm --cooldown` applies to the packages `mpm` installs.

To exercise the extension in a real session, install it from your checkout (see above), then run a nested GNOME Shell so crashes and reloads stay contained:

```shell-session
$ dbus-run-session -- gnome-shell --nested --wayland
```

Logs are visible with:

```shell-session
$ journalctl --follow --output=cat /usr/bin/gnome-shell
```

## Release process

The extension version is advertised through the `version-name` field of `metadata.json`, kept in lockstep with the `mpm` version by `bump-my-version`.

If the extension changed between releases, a fresh zip is uploaded to [extensions.gnome.org](https://extensions.gnome.org) for review. Reviews there are manual and can take a while.
