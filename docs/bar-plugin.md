# {octicon}`plug` Xbar and SwiftBar plugin

The Meta Package Manager project is actively maintaining a plugin that is both compatible with [Xbar](https://github.com/matryer/xbar) and [SwiftBar](https://github.com/swiftbar/SwiftBar).

The plugin is written in Python and is a small wrapper around the `mpm` CLI.

For Linux desktops, the {doc}`GNOME Shell extension <gnome-shell>` provides the same menu from the top bar.

Each outdated package has its version diff colored with the same convention as `mpm outdated`: unchanged prefix in gray, installed-version suffix in red, latest-version suffix in green. SwiftBar renders these colors natively (package lines carry the `ansi=true` parameter); Xbar strips the color codes and shows plain text. On the translucent menus of recent macOS releases the suffixes adapt to the menu appearance, since the default system colors lose contrast against the material: a light menu darkens both suffixes, and a dark menu brightens the green.

```{hint}
I recommend SwiftBar, because Xbar has 2 outstanding issues:
- [`=` not allowed in variables defaults](https://github.com/matryer/xbar/issues/832)
- [Shell parameters over-escaping](https://github.com/matryer/xbar/issues/831)
```

```{important}
SwiftBar `2.1.0` or newer is required: older releases mangle the variable defaults carrying an `=` sign ([swiftbar/SwiftBar#445](https://github.com/swiftbar/SwiftBar/issues/445)). The plugin detects the host version and renders an error instead of its menu below that threshold. Xbar exposes no version to its plugins, so it is not checked.
```

## Configuration

The plugin is configurable with these environment variables:

| Variable name              | Description                                                                      | Type    | Defaults             | SwiftBar support |                    Xbar support                    |
| -------------------------- | -------------------------------------------------------------------------------- | ------- | -------------------- | :--------------: | :------------------------------------------------: |
| `VAR_SUBMENU_LAYOUT`       | Group packages into a sub-menu for each manager.                                 | Boolean | `False`              |        ✅        |                         ✅                         |
| `VAR_TABLE_RENDERING`      | Aligns package names and versions in a table for easier visual parsing.          | Boolean | `True`               |        ✅        |                         ✅                         |
| `VAR_DEFAULT_FONT`         | Font parameters for regular text.                                                | String  | Empty                |        ✅        | [❌\*](https://github.com/matryer/xbar/issues/832) |
| `VAR_MONOSPACE_FONT`       | Font parameters for monospace text. Used for table rendering and error messages. | String  | `font=Menlo size=12` |        ✅        | [❌\*](https://github.com/matryer/xbar/issues/832) |
| `VAR_HIDE_WHEN_UP_TO_DATE` | Hide the menu bar icon while nothing is outdated and no manager errored.         | Boolean | `False`              |        ✅        |                         ❌                         |

```{note}
SwiftBar renders two things differently from Xbar: the outdated count sits in a native badge on each manager header rather than in its label, and the grouped layout folds every section into an inline accordion ([swiftbar/SwiftBar#480](https://github.com/swiftbar/SwiftBar/pull/480)) that expands in place without dismissing the menu. The SwiftBar screenshots below predate both.
```

These variables only drive the menu layout. Everything else comes from `mpm`'s own configuration file: the plugin passes no option beyond the ones it decides itself, so the file found at its default location on the system applies to every run it triggers. See {doc}`configuration` for the search paths and the full schema.

## Menu actions

Clicking a package runs `mpm --<manager-id> upgrade <package-id>`, and a section's *Upgrade all* entry runs `mpm --<manager-id> upgrade --all`. Neither invokes the package manager directly, so a click is subject to the same policy as the `mpm` run that rendered the menu: manager selection, {doc}`sudo` escalation, per-manager {doc}`overrides` and the release-age {doc}`cooldown` all apply.

That last one is the visible consequence: with a `cooldown` set, clicking a package of a manager that cannot enforce it natively skips it with a warning instead of upgrading it ungated. Set `policy = "best-effort"` in the `[mpm.cooldown]` table to let those managers run anyway, without the safeguard.

Both variants of each entry go through `mpm`: a plain click opens a terminal so the run can be followed, and holding the `Option` key runs it silently.

When no `mpm` is found on the system, or one older than the plugin requires, the menu carries a bootstrap pair in place of the package list: an *Install mpm … with uv* entry running `uv tool install --upgrade meta-package-manager` in a terminal, and an *Open mpm installation instructions* entry opening {doc}`install` for the systems `uv` does not answer for. The {doc}`GNOME Shell extension <gnome-shell>` offers the same pair.

## Menu markers

The plugin has no icon files of its own: every state is an emoji, which Xbar and SwiftBar render as text wherever it appears.

| Marker | Where                    | Meaning                                                                  |
| :----- | :----------------------- | :----------------------------------------------------------------------- |
| 🎁↑N   | Menu bar title           | N packages can be upgraded.                                              |
| 📦✓    | Menu bar title           | Every selected manager reports nothing to upgrade.                       |
| ⚠️N    | Menu bar title, appended | N managers reported errors during the run.                               |
| ❗️     | Menu bar title           | No runnable `mpm`: the bootstrap pair replaces the package list.         |
| ⚠️     | Manager section header   | That manager reported an error, in the sub-menu layout.                  |
| 🆙     | *Upgrade all* row        | Upgrades every outdated package of one manager.                          |

The {doc}`GNOME Shell extension <gnome-shell>` renders the same states as named icons from the desktop icon theme instead: an emoji is a font glyph a desktop theme cannot restyle, and the GNOME reviewers ask for icons.

## Screenshots

### SwiftBar

````{grid} 1 2 3 4
```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_SUBMENU_LAYOUT = False</code></span><br/><span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_TABLE_RENDERING = False</code></span>
:img-top: assets/swiftbar-flatmenu-standard-rendering.png
:link: /_images/swiftbar-flatmenu-standard-rendering.png
```

```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_SUBMENU_LAYOUT = False</code></span><br/><span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_TABLE_RENDERING = True</code></span></br>(default)
:img-top: assets/swiftbar-flatmenu-table-rendering.png
:link: /_images/swiftbar-flatmenu-table-rendering.png
```

```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_SUBMENU_LAYOUT = True</code></span><br/><span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_TABLE_RENDERING = True</code></span>
:img-top: assets/swiftbar-submenu-table-rendering.png
:link: /_images/swiftbar-submenu-table-rendering.png
```

```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_SUBMENU_LAYOUT = True</code></span><br/><span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_TABLE_RENDERING = False</code></span>
:img-top: assets/swiftbar-submenu-strandard-rendering.png
:link: /_images/swiftbar-submenu-strandard-rendering.png
```
````

### Xbar

````{grid} 1 2 3 4
```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_SUBMENU_LAYOUT = False</code></span><br/><span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_TABLE_RENDERING = False</code></span>
:img-top: assets/xbar-flatmenu-standard-rendering.png
:link: /_images/xbar-flatmenu-standard-rendering.png
```

```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_SUBMENU_LAYOUT = False</code></span><br/><span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_TABLE_RENDERING = True</code></span></br>(default)
:img-top: assets/xbar-flatmenu-table-rendering.png
:link: /_images/xbar-flatmenu-table-rendering.png
```

```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_SUBMENU_LAYOUT = True</code></span><br/><span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_TABLE_RENDERING = True</code></span>
:img-top: assets/xbar-submenu-table-rendering.png
:link: /_images/xbar-submenu-table-rendering.png
```

```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_SUBMENU_LAYOUT = True</code></span><br/><span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_TABLE_RENDERING = False</code></span>
:img-top: assets/xbar-submenu-strandard-rendering.png
:link: /_images/xbar-submenu-strandard-rendering.png
```
````

## Location

A copy of the latest stable version of the plugin is [available on Xbar website](https://xbarapp.com/docs/plugins/Dev/meta_package_manager.7h.py.html) and [plugin repository](https://github.com/matryer/xbar-plugins/blob/master/Dev/meta_package_manager.7h.py).

Once `mpm` is installed on your system, it can dynamically be located with the dedicated `--bar-plugin-path` option:

```shell-session
$ mpm --bar-plugin-path
~/Library/Python/3.11/lib/python/site-packages/meta_package_manager/bar_plugin.py
```

This option is handy for deployment and initial configuration of Xbar/SwiftBar. I [use this in my dotfiles](https://github.com/kdeldycke/dotfiles/blob/c04296d29e5f5ce48687f79554b265b3e89d5dbb/install.sh#L230) to symlink the plugin to its latest version:

```shell-session
$ ln -sf "$(mpm --bar-plugin-path)" "${HOME}/Library/Application Support/xbar/plugins/mpm.7h.py"
```

## Python `>= 3.9` required

The plugin **requires Python 3.9 or newer**, which every macOS still receiving security updates provides out of the box:

| macOS           | Released   | Security updates until[^1] | Command Line Tools | `python3`[^2] |
| --------------- | ---------- | -------------------------- | ------------------ | ------------- |
| 26.x - Tahoe    | 2025-09-15 | current                    | 26                 | 3.9.6         |
| 15.x - Sequoia  | 2024-09-16 | current                    | 16                 | 3.9.6         |
| 14.x - Sonoma   | 2023-09-26 | current                    | 15                 | 3.9.6         |
| 13.x - Ventura  | 2022-10-24 | 2025-09-15                 | 14                 | 3.9.6         |
| 12.x - Monterey | 2021-10-25 | 2024-09-16                 | 13                 | 3.8.9         |

Apple patches the current release and its two predecessors, so the three rows marked *current* are the ones a user can still be running on an up-to-date system, and all three answer `3.9.6`. Monterey is the last release that shipped a Python older than the plugin requires, and it stopped receiving updates in 2024.

The version tracks the Command Line Tools rather than macOS itself: `/usr/bin/python3` is a stub resolving to whichever toolchain is installed, which is why the table pairs each release with the toolchain it shipped alongside. Apple renumbered both to `26` in 2025, so the sequence skips from `16` to `26` and no macOS `16` was ever released.

That way, the plugin is compatible with every supported macOS out of the box, and can be run as-is without any extra dependency.

````{caution}
It looks like since Monterey (macOS), there is no default Python version installed anymore, and the `python` CLI is a stub that points to the App Store to install Xcode:

```shell-session
$ python3 --version
xcode-select: note: no developer tools were found at '/Applications/Xcode.app', requesting install. Choose an option in the dialog to download the command line developer tools.
```
````

## Development workflow

Active development of the plugin is happening here, as a side-project of {command}`mpm` itself.

Releases of the plugin are synchronized with the package. Both share the exact same version to simplify management. This explains why the plugin can appear to jump ahead a couple of major/minor versions while providing tiny or no changes at all.

A release is ready when both the package and the plugin reach a stable state.

If the plugin has been changed between releases, a [copy of the plugin is pushed](https://github.com/matryer/xbar-plugins/pulls?q=is%3Apr%20%22Meta%20Package%20Manager%22) under the name `meta_package_manager.7h.py`, to the [official Xbar plugin repository](https://github.com/matryer/xbar-plugins/blob/master/Dev/meta_package_manager.7h.py).

## Release process

1. [Fork](https://help.github.com/articles/fork-a-repo/) the official [Xbar plugin repository](https://github.com/matryer/xbar-plugins).

2. Fetch a local copy of the fork:

   ```shell-session
   $ git clone https://github.com/kdeldycke/xbar-plugins
   $ cd xbar-plugins
   ```

3. Create a new branch and switch to it:

   ```shell-session
   $ git branch "meta-package-manager-v7.6.0"
   $ git checkout "meta-package-manager-v7.6.0"
   ```

4. Replace existing copy of the plugin with the latest tagged version:

   ```shell-session
   $ wget https://raw.githubusercontent.com/kdeldycke/meta-package-manager/v7.6.0/meta_package_manager/bar_plugin.py
   $ mv ./bar_plugin.py ./Dev/meta_package_manager.7h.py
   $ chmod 755 ./Dev/meta_package_manager.7h.py
   ```

5. Commit the new plugin:

   ```shell-session
   $ git add ./Dev/meta_package_manager.7h.py
   $ git commit -m "Upgrade to Meta Package Manager plugin v7.6.0"
   ```

6. Push new branch:

   ```shell-session
   $ git push --set-upstream origin "meta-package-manager-v7.6.0"
   ```

7. [Create a pull-request](https://help.github.com/articles/creating-a-pull-request/) in the original repository.

## `meta_package_manager.bar_plugin` API

```{eval-rst}
.. automodule:: meta_package_manager.bar_plugin
   :members:
   :show-inheritance:
   :undoc-members:
```

## `meta_package_manager.bar_plugin_renderer` API

```{eval-rst}
.. automodule:: meta_package_manager.bar_plugin_renderer
   :members:
   :show-inheritance:
   :undoc-members:
```

[^1]: Source: [https://endoflife.date/macos](https://endoflife.date/macos)

[^2]: Source: [https://ihaveahax.net/wiki/Python_version_information#Xcode\_(macOS)](https://ihaveahax.net/wiki/Python_version_information#Xcode_(macOS)), whose table is keyed by toolchain version.
