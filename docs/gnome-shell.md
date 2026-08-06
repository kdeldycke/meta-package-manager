# {octicon}`plug` GNOME Shell extension

The Meta Package Manager project maintains a GNOME Shell extension, the Linux desktop counterpart of the {doc}`Xbar/SwiftBar plugin <bar-plugin>`.

A top bar indicator lists the outdated packages reported by `mpm outdated` across every package manager on the system, and lets you upgrade them one by one or per manager. Each outdated package has its version diff colored with the same convention as `mpm outdated`: unchanged prefix in gray, installed-version suffix in red, latest-version suffix in green.

The extension is a frontend to the `mpm` CLI, which must be installed separately: see {doc}`install`. It looks for `mpm` on the session `PATH`, then in well-known locations (`~/.local/bin`, `/usr/local/bin`, Linuxbrew), and a custom launcher (like `uv run mpm`) can be configured in its settings. `mpm` `6.4.0` or newer is required.

## Requirements

- GNOME Shell `46` to `50`.
- The `mpm` CLI, `6.4.0` or newer, reachable from the GNOME session.
- For upgrades run in a terminal: any of `xdg-terminal-exec`, Ptyxis, Console (`kgx`) or GNOME Terminal, or a custom terminal command set in the extension settings.

## Installation

### From extensions.gnome.org

The extension is pending review on [extensions.gnome.org](https://extensions.gnome.org). Once published, it will be installable with one click from the site.

### From a release zip

Each change to the extension produces an installable zip artifact via the [`tests-gnome-extension.yaml` workflow](https://github.com/kdeldycke/meta-package-manager/actions/workflows/tests-gnome-extension.yaml). Download it, then:

```shell-session
$ gnome-extensions install --force mpm@kdeldycke.github.io.shell-extension.zip
$ gnome-extensions enable mpm@kdeldycke.github.io
```

Log out and back in (or restart GNOME Shell) for the extension to load.

### From a source checkout

```shell-session
$ git clone https://github.com/kdeldycke/meta-package-manager.git
$ cd ./meta-package-manager
$ glib-compile-schemas "gnome-shell/mpm@kdeldycke.github.io/schemas/"
$ ln -snf "$(pwd)/gnome-shell/mpm@kdeldycke.github.io" ~/.local/share/gnome-shell/extensions/
$ gnome-extensions enable mpm@kdeldycke.github.io
```

## Configuration

Settings live in the extension preferences window (also reachable from the indicator menu) and mirror the {doc}`Xbar/SwiftBar plugin variables <bar-plugin>` where an equivalent exists:

| Setting                | Description                                                     | Type    | Default | Xbar/SwiftBar equivalent       |
| ---------------------- | --------------------------------------------------------------- | ------- | ------- | ------------------------------ |
| `submenu-layout`       | Group packages into a sub-menu for each manager.                | Boolean | `false` | `VAR_SUBMENU_LAYOUT`           |
| `check-interval`       | Minutes between two package checks.                             | Integer | `420`   | The `mpm.7h.py` filename cycle |
| `boot-wait`            | Seconds before the first check after login.                     | Integer | `30`    | :                              |
| `timeout`              | Seconds passed to `mpm --timeout` for background checks.        | Integer | `60`    | Hard-coded to the same `60`    |
| `mpm-command`          | Custom `mpm` launcher, empty to autodetect.                     | String  | Empty   | The `search_mpm` tiers         |
| `always-visible`       | Show the indicator even when everything is up to date.          | Boolean | `true`  | :                              |
| `show-count`           | Show the outdated package count next to the icon.               | Boolean | `true`  | The `🎁↑N` title counter       |
| `notify`               | Desktop notification when new outdated packages appear.         | Boolean | `false` | :                              |
| `upgrade-in-terminal`  | Run upgrades in a terminal window.                              | Boolean | `true`  | `terminal=true` menu items     |
| `terminal-command`     | Custom terminal emulator, empty to autodetect.                  | String  | Empty   | :                              |
| `post-upgrade-recheck` | Seconds before refreshing the list after an upgrade is started. | Integer | `300`   | The bar apps' `refresh=true`   |

`VAR_TABLE_RENDERING` and the font variables have no equivalent: the GNOME menu is built from native widgets, already aligned in columns and styled by the shell theme.

These settings only drive the menu layout and check cadence. Everything else comes from `mpm`'s own configuration file: the extension passes no option beyond the ones it decides itself, so the file found at its default location on the system applies to every run it triggers. See {doc}`configuration` for the search paths and the full schema.

## Menu actions

Clicking a package runs `mpm --{manager-id} upgrade {package-id}`, and a section's *Upgrade all* entry runs `mpm --{manager-id} upgrade --all`, exactly like the {doc}`Xbar/SwiftBar plugin menu <bar-plugin>`. Neither invokes the package manager directly, so a click is subject to the same policy as the `mpm` run that rendered the menu: manager selection, {doc}`sudo` escalation, per-manager {doc}`overrides` and the release-age {doc}`cooldown` all apply.

By default the command opens in a terminal window, so the run can be followed and `sudo` can prompt for a password. Turning `upgrade-in-terminal` off runs upgrades silently in the background: system package managers then need passwordless escalation, as `mpm` cannot prompt without a terminal. See the `NOPASSWD` guidance in {doc}`sudo`.

Since a terminal window detaches from the process actually running the upgrade, the extension cannot tell when it completes: it refreshes the package list a few minutes after launching one (`post-upgrade-recheck`), and a *Check now* entry forces a refresh at any time.

## Development workflow

The extension lives in the [`gnome-shell/` directory](https://github.com/kdeldycke/meta-package-manager/tree/main/gnome-shell) of the `mpm` repository and shares its version, release cycle and issue tracker.

Its logic is split like the bar plugin's: `extension.js` owns the widgetry while `mpm.js` is shell-free (it never imports `resource:///org/gnome/shell/*` modules), so the latter runs under a bare `gjs` interpreter:

```shell-session
$ gjs -m tests/gnome/run-tests.js
ok 1 - parseVersion nominal
(...)
```

Static invariants (metadata, GSettings schema, stylesheet and icon drift) are enforced by `tests/test_gnome_extension.py` in the regular Python test suite. Both run in CI via the [`tests-gnome-extension.yaml` workflow](https://github.com/kdeldycke/meta-package-manager/actions/workflows/tests-gnome-extension.yaml), which also packs the installable zip.

To exercise the extension in a real session, install it from your checkout (see above), then run a nested GNOME Shell so crashes and reloads stay contained:

```shell-session
$ dbus-run-session -- gnome-shell --nested --wayland
```

Logs are visible with:

```shell-session
$ journalctl --follow --output=cat /usr/bin/gnome-shell
```

## Release process

The extension version is advertised through the `version-name` field of `metadata.json`, kept in lockstep with the `mpm` version by `bump-my-version` (like the `<xbar.version>` header of the bar plugin).

If the extension changed between releases, a fresh zip is uploaded to [extensions.gnome.org](https://extensions.gnome.org) for review. Reviews there are manual and can take a while.
