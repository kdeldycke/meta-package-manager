# {octicon}`plug` SwiftBar & Xbar plugin

The Meta Package Manager project is actively maintaining a plugin that is both compatible with [SwiftBar](https://github.com/swiftbar/SwiftBar) and [Xbar](https://github.com/matryer/xbar).

The plugin is written in Python and is a small wrapper around the `mpm` CLI. It is one of the two {doc}`desktop menus <desktop-menus>` the project maintains, and that page holds what the two have in common.

SwiftBar renders the [version-diff colors](desktop-menus.md#version-diffs) natively (package lines carry the `ansi=true` parameter); Xbar strips the color codes and shows plain text. On the translucent menus of recent macOS releases the suffixes adapt to the menu appearance, since the default system colors lose contrast against the material: a light menu darkens both suffixes, and a dark menu brightens the green.

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
| `VAR_GROUP_BY_MANAGER`       | Group each manager's packages into a section of its own.                         | Boolean | `False`              |        ✅        |                         ✅                         |
| `VAR_TABLE_RENDERING`      | Aligns package names and versions in a table for easier visual parsing.          | Boolean | `True`               |        ✅        |                         ✅                         |
| `VAR_DEFAULT_FONT`         | Font parameters for regular text.                                                | String  | Empty                |        ✅        | [❌\*](https://github.com/matryer/xbar/issues/832) |
| `VAR_MONOSPACE_FONT`       | Font parameters for monospace text. Used for table rendering and error messages. | String  | `font=Menlo size=12` |        ✅        | [❌\*](https://github.com/matryer/xbar/issues/832) |
| `VAR_HIDE_WHEN_UP_TO_DATE` | Hide the menu bar icon while nothing is outdated and no manager errored.         | Boolean | `False`              |        ✅        |                         ❌                         |

```{note}
SwiftBar renders two things differently from Xbar: the outdated count sits in a native badge on each manager header rather than in its label, and the grouped layout folds every section into an inline accordion ([swiftbar/SwiftBar#480](https://github.com/swiftbar/SwiftBar/pull/480)) that expands in place without dismissing the menu. Both are visible in the screenshots below.
```

These variables only drive the menu layout: everything else comes from `mpm`'s own configuration, as {doc}`desktop-menus` explains.

## Menu actions

A click runs `mpm` rather than the package manager, and inherits the policy of the run that rendered the menu: see {doc}`desktop-menus`. Both variants of each entry go through it, and the modifier picks between them: a plain click opens a terminal so the run can be followed, and holding the `Option` key runs it silently.

## Menu markers

The plugin has no icon files of its own: every state is an emoji, which SwiftBar and Xbar render as text wherever it appears.

| Marker | Where                    | Meaning                                                                  |
| :----- | :----------------------- | :----------------------------------------------------------------------- |
| 🎁↑N   | Menu bar title           | N packages can be upgraded.                                              |
| 📦✓    | Menu bar title           | Every selected manager reports nothing to upgrade.                       |
| ⚠️N    | Menu bar title, appended | N managers reported errors during the run.                               |
| ❗️     | Menu bar title           | No runnable `mpm`: the bootstrap pair replaces the package list.         |
| ⚠️     | Manager section header   | That manager reported an error, in the sub-menu layout.                  |
| 🆙     | *Upgrade all* row        | Upgrades every outdated package of one manager.                          |

The {doc}`GNOME Shell extension <gnome-shell>` names an icon for each of these states instead, and the [panel icons table](gnome-shell.md#panel-icons) lines the two vocabularies up.

## Screenshots

Each layout is captured in both system appearances, and the tabs are synchronized so switching one switches the others.
The menu chrome is the host's, and only the version diff is the plugin's: its colors have to stay legible on either appearance, which is what the palette of {meth}`~meta_package_manager.bar_plugin_renderer.BarPluginRenderer.menu_diff_colors` is picked for.

### SwiftBar

``````{tab-set}
`````{tab-item} Light
:sync: light

````{grid} 1 2 2 2
```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_GROUP_BY_MANAGER = False</code></span><br/><span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_TABLE_RENDERING = False</code></span>
:img-top: assets/swiftbar-flat-standard-rendering-light.png
:link: /_images/swiftbar-flat-standard-rendering-light.png
```

```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_GROUP_BY_MANAGER = False</code></span><br/><span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_TABLE_RENDERING = True</code></span></br>(default)
:img-top: assets/swiftbar-flat-table-rendering-light.png
:link: /_images/swiftbar-flat-table-rendering-light.png
```

```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_GROUP_BY_MANAGER = True</code></span><br/><span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_TABLE_RENDERING = True</code></span>
:img-top: assets/swiftbar-grouped-table-rendering-light.png
:link: /_images/swiftbar-grouped-table-rendering-light.png
```

```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_GROUP_BY_MANAGER = True</code></span><br/><span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_TABLE_RENDERING = False</code></span>
:img-top: assets/swiftbar-grouped-standard-rendering-light.png
:link: /_images/swiftbar-grouped-standard-rendering-light.png
```
````
`````

`````{tab-item} Dark
:sync: dark

````{grid} 1 2 2 2
```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_GROUP_BY_MANAGER = False</code></span><br/><span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_TABLE_RENDERING = False</code></span>
:img-top: assets/swiftbar-flat-standard-rendering-dark.png
:link: /_images/swiftbar-flat-standard-rendering-dark.png
```

```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_GROUP_BY_MANAGER = False</code></span><br/><span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_TABLE_RENDERING = True</code></span></br>(default)
:img-top: assets/swiftbar-flat-table-rendering-dark.png
:link: /_images/swiftbar-flat-table-rendering-dark.png
```

```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_GROUP_BY_MANAGER = True</code></span><br/><span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_TABLE_RENDERING = True</code></span>
:img-top: assets/swiftbar-grouped-table-rendering-dark.png
:link: /_images/swiftbar-grouped-table-rendering-dark.png
```

```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_GROUP_BY_MANAGER = True</code></span><br/><span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_TABLE_RENDERING = False</code></span>
:img-top: assets/swiftbar-grouped-standard-rendering-dark.png
:link: /_images/swiftbar-grouped-standard-rendering-dark.png
```
````
`````
``````

### Xbar

``````{tab-set}
`````{tab-item} Light
:sync: light

````{grid} 1 2 2 2
```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_GROUP_BY_MANAGER = False</code></span><br/><span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_TABLE_RENDERING = False</code></span>
:img-top: assets/xbar-flat-standard-rendering-light.png
:link: /_images/xbar-flat-standard-rendering-light.png
```

```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_GROUP_BY_MANAGER = False</code></span><br/><span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_TABLE_RENDERING = True</code></span></br>(default)
:img-top: assets/xbar-flat-table-rendering-light.png
:link: /_images/xbar-flat-table-rendering-light.png
```

```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_GROUP_BY_MANAGER = True</code></span><br/><span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_TABLE_RENDERING = True</code></span>
:img-top: assets/xbar-grouped-table-rendering-light.png
:link: /_images/xbar-grouped-table-rendering-light.png
```

```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_GROUP_BY_MANAGER = True</code></span><br/><span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_TABLE_RENDERING = False</code></span>
:img-top: assets/xbar-grouped-standard-rendering-light.png
:link: /_images/xbar-grouped-standard-rendering-light.png
```
````
`````

`````{tab-item} Dark
:sync: dark

````{grid} 1 2 2 2
```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_GROUP_BY_MANAGER = False</code></span><br/><span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_TABLE_RENDERING = False</code></span>
:img-top: assets/xbar-flat-standard-rendering-dark.png
:link: /_images/xbar-flat-standard-rendering-dark.png
```

```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_GROUP_BY_MANAGER = False</code></span><br/><span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_TABLE_RENDERING = True</code></span></br>(default)
:img-top: assets/xbar-flat-table-rendering-dark.png
:link: /_images/xbar-flat-table-rendering-dark.png
```

```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_GROUP_BY_MANAGER = True</code></span><br/><span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_TABLE_RENDERING = True</code></span>
:img-top: assets/xbar-grouped-table-rendering-dark.png
:link: /_images/xbar-grouped-table-rendering-dark.png
```

```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_GROUP_BY_MANAGER = True</code></span><br/><span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_TABLE_RENDERING = False</code></span>
:img-top: assets/xbar-grouped-standard-rendering-dark.png
:link: /_images/xbar-grouped-standard-rendering-dark.png
```
````
`````
``````

## Location

Once `mpm` is installed on your system, the plugin ships with it and its path is printed by the dedicated `--bar-plugin-path` option:

```shell-session
$ mpm --bar-plugin-path
~/Library/Python/3.11/lib/python/site-packages/meta_package_manager/bar_plugin.py
```

Symlinking that path into the host's plugin folder is what keeps the menu on the latest plugin: every `mpm` upgrade is then picked up with no further action. That is [how my dotfiles install it](https://github.com/kdeldycke/dotfiles/blob/8e1fa1f8223e9a1c2cbaef8286480d2b148ead23/install.sh#L341-L357).

Where that folder is, and how it is set, differs between the two hosts:

`````{tab-set}

````{tab-item} SwiftBar
:sync: swiftbar

SwiftBar has no default plugin folder: it asks for one on first launch, then imports every file it finds there, traversing nested folders and symlinks.

`~/.swiftbar` is the conventional choice:

```shell-session
$ mkdir -p ~/.swiftbar
$ ln -sf "$(mpm --bar-plugin-path)" ~/.swiftbar/meta_package_manager.7h.py
```

SwiftBar's folder picker hides dotted folders, so point the app at it either by typing the path into that picker, or by writing the preference by hand. A running SwiftBar rewrites its preferences from memory when it quits, so that write only sticks while the app is stopped:

```shell-session
$ killall SwiftBar
$ defaults write com.ameba.SwiftBar PluginDirectory -string "${HOME}/.swiftbar"
$ open -a SwiftBar
```

```{warning}
Do not use `~/Library/Application Support/SwiftBar/Plugins`, tempting as the name is. That is SwiftBar's own data directory, in which it keeps a state and a cache folder per plugin ([swiftbar/SwiftBar#522](https://github.com/swiftbar/SwiftBar/issues/522)). Pointing the plugin folder at it makes SwiftBar scan the tree it writes into, and import its own output as plugins.
```

```{important}
`~/.swiftbar` needs SwiftBar `2.1.1` or newer. `2.1.0` introduced packaged `.swiftbar` plugin bundles and recognized them by the folder name, so it took the whole `.swiftbar` root for one bundle and skipped every file inside it as *not a regular file* ([swiftbar/SwiftBar#508](https://github.com/swiftbar/SwiftBar/issues/508)).
```
````

````{tab-item} Xbar
:sync: xbar

Xbar's plugin folder is fixed at `~/Library/Application Support/xbar/plugins`:

```shell-session
$ ln -sf "$(mpm --bar-plugin-path)" "${HOME}/Library/Application Support/xbar/plugins/meta_package_manager.7h.py"
```

A copy of the latest stable release is also [published on the Xbar website](https://xbarapp.com/docs/plugins/Dev/meta_package_manager.7h.py.html) and in its [plugin repository](https://github.com/matryer/xbar-plugins/blob/master/Dev/meta_package_manager.7h.py), so it can be installed from Xbar's own plugin browser. That copy is only refreshed on `mpm` releases, so it lags behind the symlink above.
````

`````

## Python `>= 3.9` required

The plugin **requires Python 3.9 or newer**, and runs on the interpreter macOS provides, without any extra dependency.

macOS ships no Python of its own: `/usr/bin/python3` is a stub that runs the interpreter bundled with the Command Line Tools, and offers to install them when they are missing:

```shell-session
$ python3 --version
xcode-select: note: no developer tools were found at '/Applications/Xcode.app', requesting install. Choose an option in the dialog to download the command line developer tools.
```

The version that answers therefore tracks the Command Line Tools, not the macOS release:

| macOS           | Released   | Security updates until[^1] | Command Line Tools | `python3`[^2] |
| --------------- | ---------- | -------------------------- | ------------------ | ------------- |
| 26.x - Tahoe    | 2025-09-15 | current                    | 26                 | 3.9.6         |
| 15.x - Sequoia  | 2024-09-16 | current                    | 16                 | 3.9.6         |
| 14.x - Sonoma   | 2023-09-26 | current                    | 15                 | 3.9.6         |
| 13.x - Ventura  | 2022-10-24 | 2025-09-15                 | 14                 | 3.9.6         |
| 12.x - Monterey | 2021-10-25 | 2024-09-16                 | 13                 | 3.8.9         |

Every macOS still receiving security updates answers `3.9.6`. Monterey is the only release below the requirement, and it stopped receiving updates in 2024.

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
