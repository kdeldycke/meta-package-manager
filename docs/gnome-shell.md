# {octicon}`plug` GNOME Shell extension

The Meta Package Manager project maintains a GNOME Shell extension.

A top bar indicator lists the outdated packages reported by `mpm outdated` across every package manager on the system, and lets you upgrade them one by one or per manager. The `mpm` CLI is installed separately: see {doc}`install`.

Each outdated package carries its version diff colored with the same convention as `mpm outdated`: unchanged prefix in gray, installed-version suffix in red, latest-version suffix in green.

The extension looks for `mpm` on the session `PATH`, then in well-known locations (`~/.local/bin`, `/usr/local/bin`, Linuxbrew), and a custom launcher (like `uv run mpm`) can be configured in its settings. `mpm` `6.4.0` or newer is required.

## Requirements

- GNOME Shell `46` to `50`.
- The `mpm` CLI, `6.4.0` or newer, reachable from the GNOME session.
- For upgrades run in a terminal: any of `xdg-terminal-exec`, Ptyxis, Console (`kgx`) or GNOME Terminal, or a custom terminal command set in the extension settings.

## Installation

### From extensions.gnome.org

```{todo}
The extension is not yet published on [extensions.gnome.org](https://extensions.gnome.org). Once it lands there, it will be installable with one click from the site. Until then, use one of the methods below.
```

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

``````{tab-set}
`````{tab-item} Light
:sync: light

```{image} assets/gnome-shell-preferences-light.png
:alt: The preferences window of the GNOME Shell extension
:align: center
:scale: 50
```
`````

`````{tab-item} Dark
:sync: dark

```{image} assets/gnome-shell-preferences-dark.png
:alt: The preferences window of the GNOME Shell extension
:align: center
:scale: 50
```
`````
``````

| Setting                | Description                                                     | Type    | Default |
| ---------------------- | --------------------------------------------------------------- | ------- | ------- |
| `group-by-manager`     | Group each manager's packages into a section of its own.        | Boolean | `true`  |
| `align-columns`        | Center each version pair around its arrow, monospaced.          | Boolean | `true`  |
| `check-interval`       | Minutes between two package checks.                             | Integer | `420`   |
| `boot-wait`            | Seconds before the first check after login.                     | Integer | `30`    |
| `timeout`              | Seconds passed to `mpm --timeout` for background checks.        | Integer | `60`    |
| `mpm-command`          | Custom `mpm` launcher, empty to autodetect.                     | String  | Empty   |
| `mpm-options`          | Extra options for every `mpm` call, before the subcommand.      | String  | Empty   |
| `always-visible`       | Show the indicator even when everything is up to date.          | Boolean | `true`  |
| `show-count`           | Show the outdated package count next to the icon.               | Boolean | `true`  |
| `notify`               | Desktop notification when new outdated packages appear.         | Boolean | `false` |
| `upgrade-in-terminal`  | Run upgrades in a terminal window.                              | Boolean | `true`  |
| `terminal-command`     | Custom terminal emulator, empty to autodetect.                  | String  | Empty   |
| `post-upgrade-recheck` | Seconds before refreshing the list after an upgrade is started. | Integer | `300`   |

These settings drive the menu layout, the check cadence and how `mpm` is called: everything else comes from `mpm`'s own configuration file, which applies to every run the extension triggers. See {doc}`configuration` for the search paths and the full schema.

`mpm-options` goes after the extension's own options, so an option set twice takes the value given here. That includes `--verbosity`, which the extension sets to `CRITICAL` to list the outdated packages. A raised level never hides that list: only the exit status of `mpm` marks a check as failed. A successful check drops what `mpm` wrote to standard error. An upgrade run in a terminal shows its log there.

The *About* group at the foot of the window names two versions. The first is the extension's own, compiled into its `metadata.json`. The second is the `mpm` release the extension resolved, with the command that answered it below. The two ship separately, so a bug report needs both.

## Panel icons

| State             |                                                                      Adwaita                                                                      |                                                                     Yaru                                                                      | Icon name                            | Shown when                                                   |
| :---------------- | :-----------------------------------------------------------------------------------------------------------------------------------------------: | :-------------------------------------------------------------------------------------------------------------------------------------------: | :----------------------------------- | :----------------------------------------------------------- |
| Unknown           |      <img src="https://raw.githubusercontent.com/StorageB/icons/main/GNOME48Adwaita/neutral/status/content-loading-symbolic.svg" width="18">      |      <img src="https://raw.githubusercontent.com/ubuntu/yaru/master/icons/Yaru/scalable/status/content-loading-symbolic.svg" width="18">      | `content-loading-symbolic`           | Before the first check of the session.                       |
| Checking          |       <img src="https://raw.githubusercontent.com/StorageB/icons/main/GNOME48Adwaita/neutral/actions/view-refresh-symbolic.svg" width="18">       |       <img src="https://raw.githubusercontent.com/ubuntu/yaru/master/icons/Yaru/scalable/actions/view-refresh-symbolic.svg" width="18">       | `view-refresh-symbolic`              | While a check is running.                                    |
| Up to date        |      <img src="https://raw.githubusercontent.com/StorageB/icons/main/GNOME48Adwaita/neutral/actions/selection-mode-symbolic.svg" width="18">      |      <img src="https://raw.githubusercontent.com/ubuntu/yaru/master/icons/Yaru/scalable/emblems/emblem-default-symbolic.svg" width="18">      | `selection-mode-symbolic`            | No selected manager reports an upgrade.                      |
| Updates available | <img src="https://raw.githubusercontent.com/StorageB/icons/main/GNOME48Adwaita/neutral/status/software-update-available-symbolic.svg" width="18"> | <img src="https://raw.githubusercontent.com/ubuntu/yaru/master/icons/Yaru/scalable/status/software-update-available-symbolic.svg" width="18"> | `software-update-available-symbolic` | Packages can be upgraded. Also marks each *Upgrade all* row. |
| Error             |  <img src="https://raw.githubusercontent.com/StorageB/icons/main/GNOME48Adwaita/neutral/status/software-update-urgent-symbolic.svg" width="18">   |  <img src="https://raw.githubusercontent.com/ubuntu/yaru/master/icons/Yaru/scalable/status/software-update-urgent-symbolic.svg" width="18">   | `software-update-urgent-symbolic`    | A check failed, or no runnable `mpm` was found.              |
| Manager failed    |      <img src="https://raw.githubusercontent.com/StorageB/icons/main/GNOME48Adwaita/neutral/status/dialog-warning-symbolic.svg" width="18">       |     <img src="https://raw.githubusercontent.com/ubuntu/yaru/master/icons/Yaru/scalable/generic-symbols/warning-symbolic.svg" width="18">      | `dialog-warning-symbolic`            | On the sub-menu header of a manager that reported errors.    |

Both previews are shown from the upstream repositories. Browse the full [Adwaita](https://github.com/StorageB/icons/blob/main/GNOME48Adwaita/icons.md) and [Yaru](https://github.com/StorageB/icons/blob/main/Yaru/icons.md) icon lists.

## Menu actions

Clicking a package runs `mpm --<manager-id> upgrade pkg:<manager-id>/<package-id>`, and a section's *Upgrade all* entry runs `mpm --<manager-id> upgrade --all`. The pURL ties the package to its section's manager, so `mpm` upgrades it without first looking for it in the installed packages. Neither command invokes the package manager directly, so a click is subject to the same policy as the `mpm` run that rendered the menu: manager selection, {doc}`sudo` escalation, per-manager {doc}`overrides` and the release-age {doc}`cooldown` all apply.

With a `cooldown` set, clicking a package of a manager that cannot enforce it natively skips it with a warning instead of upgrading it ungated. Set `policy = "best-effort"` in the `[mpm.cooldown]` table to let those managers run anyway, without the safeguard.

By default the command opens in a terminal window, so the run can be followed and `sudo` can prompt for a password. Turning `upgrade-in-terminal` off runs upgrades silently in the background: system package managers then need passwordless escalation, as `mpm` cannot prompt without a terminal. See the `NOPASSWD` guidance in {doc}`sudo`.

Since a terminal window detaches from the process actually running the upgrade, the extension cannot tell when it completes: it refreshes the package list a few minutes after launching one (`post-upgrade-recheck`), and a *Check now* entry forces a refresh at any time. A package stays clickable while its upgrade runs: an upgrade you cancelled, or whose terminal you closed too early, can be started again at once, and clicking one that already succeeded is a no-op every manager absorbs. An upgrade run with *Run upgrades in a terminal* off needs none of this waiting: nothing detaches there, so the list refreshes as soon as the upgrade exits. That entry greys out and reads *Checking…* while a check runs, which is the menu half of the panel state above.

A missing `mpm` puts a bootstrap pair in place of the package list: an *Install mpm with uv* entry running `uv tool install --upgrade meta-package-manager`, and an *Open mpm installation instructions* entry opening {doc}`install` for the systems `uv` does not answer for. Both open through the same terminal path as an upgrade.

## Screenshots

Every layout, photographed from a real GNOME session driven by `docs/gnome_screenshots_update.py` and refreshed by [`docs-screenshots.yaml`](https://github.com/kdeldycke/meta-package-manager/blob/main/.github/workflows/docs-screenshots.yaml) whenever the extension changes.
Each one is captured in both shell appearances, so the two are there to be compared rather than picked for you: the shell restyles its menu with the desktop's light or dark preference, and the version diff has to keep its colors legible on both. The tabs are synchronized, so switching one switches the other.

The menu has two layout switches, both set in the preferences window above. `group-by-manager` lists every manager's packages inline under a header counting them, or gives each manager a section that expands on a click: the captures unfold the first one. `align-columns` sets each version pair in a monospaced font, centered on its arrow; off, the pair sits flush right in the menu's own font.
The `flatpak` section also carries a manager error, which the flat layout renders as a monospace red line under the packages that did resolve, and the grouped one flags with the `dialog-warning-symbolic` icon documented above.
The report scrolls past a set height instead of growing the menu to the screen, and the flat captures show that as it is: the list stops at its fold, under a scrollbar, and the sections below it are reached with the wheel.

```````{tab-set}
``````{tab-item} Light
:sync: light

`````{grid} 1 2 2 2
````{grid-item}
<span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>group-by-manager = false</code></span><br/><span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>align-columns = false</code></span>

```{image} assets/gnome-shell-flat-standard-rendering-light.png
:alt: The extension's menu listing outdated packages inline, one header per package manager, with one manager's error shown in red, each version pair flush right in the menu font
:align: center
:scale: 50
```
````

````{grid-item}
<span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>group-by-manager = false</code></span><br/><span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>align-columns = true</code></span>

```{image} assets/gnome-shell-flat-table-rendering-light.png
:alt: The extension's menu listing outdated packages inline, one header per package manager, with one manager's error shown in red, each version pair centered on its arrow in a monospaced font
:align: center
:scale: 50
```
````

````{grid-item}
<span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>group-by-manager = true</code></span><br/><span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>align-columns = true</code></span><br/>(default)

```{image} assets/gnome-shell-grouped-table-rendering-light.png
:alt: The extension's menu with one section per package manager, the first one unfolded, the failing one carrying a warning icon, each version pair centered on its arrow in a monospaced font
:align: center
:scale: 50
```
````

````{grid-item}
<span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>group-by-manager = true</code></span><br/><span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>align-columns = false</code></span>

```{image} assets/gnome-shell-grouped-standard-rendering-light.png
:alt: The extension's menu with one section per package manager, the first one unfolded, the failing one carrying a warning icon, each version pair flush right in the menu font
:align: center
:scale: 50
```
````
`````
``````

``````{tab-item} Dark
:sync: dark

`````{grid} 1 2 2 2
````{grid-item}
<span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>group-by-manager = false</code></span><br/><span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>align-columns = false</code></span>

```{image} assets/gnome-shell-flat-standard-rendering-dark.png
:alt: The extension's menu listing outdated packages inline, one header per package manager, with one manager's error shown in red, each version pair flush right in the menu font
:align: center
:scale: 50
```
````

````{grid-item}
<span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>group-by-manager = false</code></span><br/><span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>align-columns = true</code></span>

```{image} assets/gnome-shell-flat-table-rendering-dark.png
:alt: The extension's menu listing outdated packages inline, one header per package manager, with one manager's error shown in red, each version pair centered on its arrow in a monospaced font
:align: center
:scale: 50
```
````

````{grid-item}
<span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>group-by-manager = true</code></span><br/><span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>align-columns = true</code></span><br/>(default)

```{image} assets/gnome-shell-grouped-table-rendering-dark.png
:alt: The extension's menu with one section per package manager, the first one unfolded, the failing one carrying a warning icon, each version pair centered on its arrow in a monospaced font
:align: center
:scale: 50
```
````

````{grid-item}
<span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>group-by-manager = true</code></span><br/><span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>align-columns = false</code></span>

```{image} assets/gnome-shell-grouped-standard-rendering-dark.png
:alt: The extension's menu with one section per package manager, the first one unfolded, the failing one carrying a warning icon, each version pair flush right in the menu font
:align: center
:scale: 50
```
````
`````
``````
```````

## Development workflow

The extension lives in the [`gnome-shell/` directory](https://github.com/kdeldycke/meta-package-manager/tree/main/gnome-shell) of the `mpm` repository and shares its version, release cycle and issue tracker.

Its logic is split in two: `extension.js` owns the widgetry while `mpm.js` is shell-free (it never imports `resource:///org/gnome/shell/*` modules), so the latter runs under a bare `gjs` interpreter:

```shell-session
$ gjs -m tests/gnome/run-tests.js
ok 1 - parseVersion nominal
(...)
```

Static invariants (metadata, GSettings schema, stylesheet and icon drift) are enforced by `tests/test_gnome_extension.py` in the regular Python test suite. The [`tests-gnome-extension.yaml` workflow](https://github.com/kdeldycke/meta-package-manager/actions/workflows/tests-gnome-extension.yaml) runs the gjs suite, checks the sources with [`shexli`](https://pypi.org/project/shexli/) (the static analyzer extensions.gnome.org applies to every upload), packs the installable zip with `gnome-extensions pack`, and proves it installs with a `gnome-extensions install` round-trip.

```{todo}
Drop the `tree-sitter==0.25.2` pin the `shexli` job carries once the analyzer caps that dependency itself. `shexli` declares `tree-sitter>=0.25.0` with no ceiling, so a fresh install pairs core `0.26.0` with the `0.25.0` grammar, the newest `tree-sitter-javascript` published, and that pair segfaults on this extension every time. Tracked upstream as [extensions-web#398](https://gitlab.gnome.org/Infrastructure/extensions-web/-/issues/398).
```

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

## Changelog

```{python:render}
from meta_package_manager._docs import scope_changelog

print(scope_changelog("gnome-shell"))
```
