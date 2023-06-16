# Xbar and SwiftBar plugin

The Meta Package Manager project is actively maintaining a plugin that is both compatible with
[Xbar](https://github.com/matryer/xbar) and [SwiftBar](https://github.com/swiftbar/SwiftBar).

The plugin is written in Python and is a small wrapper around the `mpm` CLI.

```{hint}
I recommend SwiftBar, because Xbar has 2 outstanding issues:
- [`=` not allowed in variables defaults](https://github.com/matryer/xbar/issues/832)
- [Shell parameters over-escaping](https://github.com/matryer/xbar/issues/831)
```

## Configuration

The plugin is configurable with these environment variables:

| Variable name         | Description                                                                               | Type    | Defaults             | SwiftBar support |                   Xbar support                    |
| --------------------- | ----------------------------------------------------------------------------------------- | ------- | -------------------- | :--------------: | :-----------------------------------------------: |
| `VAR_SUBMENU_LAYOUT`  | Group packages into a sub-menu for each manager.                                          | Boolean | `False`              |        ✅         |                         ✅                         |
| `VAR_TABLE_RENDERING` | Aligns package names and versions in a table for easier visual parsing.                   | Boolean | `True`               |        ✅         |                         ✅                         |
| `VAR_DEFAULT_FONT`    | Default font to use for non-monospaced text.                                              | String  | Empty                |        ✅         | [❌\*](https://github.com/matryer/xbar/issues/832) |
| `VAR_MONOSPACE_FONT`  | Default configuration for monospace fonts, including errors. Is used for table rendering. | String  | `font=Menlo size=12` |        ✅         | [❌\*](https://github.com/matryer/xbar/issues/832) |

## Screenshots

### SwiftBar

````{grid} 1 2 3 4
```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_SUBMENU_LAYOUT = False</code></span><br/><span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_TABLE_RENDERING = False</code></span>
:img-top: assets/swiftbar-flatmenu-standard-rendering.png
:link: assets/swiftbar-flatmenu-standard-rendering.png
```

```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_SUBMENU_LAYOUT = False</code></span><br/><span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_TABLE_RENDERING = True</code></span></br>(default)
:img-top: assets/swiftbar-flatmenu-table-rendering.png
:link: assets/swiftbar-flatmenu-table-rendering.png
```

```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_SUBMENU_LAYOUT = True</code></span><br/><span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_TABLE_RENDERING = True</code></span>
:img-top: assets/swiftbar-submenu-table-rendering.png
:link: assets/swiftbar-submenu-table-rendering.png
```

```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_SUBMENU_LAYOUT = True</code></span><br/><span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_TABLE_RENDERING = False</code></span>
:img-top: assets/swiftbar-submenu-strandard-rendering.png
:link: assets/swiftbar-submenu-strandard-rendering.png
```
````

### Xbar

````{grid} 1 2 3 4
```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_SUBMENU_LAYOUT = False</code></span><br/><span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_TABLE_RENDERING = False</code></span>
:img-top: assets/xbar-flatmenu-standard-rendering.png
:link: assets/xbar-flatmenu-standard-rendering.png
```

```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_SUBMENU_LAYOUT = False</code></span><br/><span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_TABLE_RENDERING = True</code></span></br>(default)
:img-top: assets/xbar-flatmenu-table-rendering.png
:link: assets/xbar-flatmenu-table-rendering.png
```

```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_SUBMENU_LAYOUT = True</code></span><br/><span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_TABLE_RENDERING = True</code></span>
:img-top: assets/xbar-submenu-table-rendering.png
:link: assets/xbar-submenu-table-rendering.png
```

```{grid-item-card} <span class="sd-sphinx-override sd-badge sd-bg-success sd-bg-text-success"><code>VAR_SUBMENU_LAYOUT = True</code></span><br/><span class="sd-sphinx-override sd-badge sd-outline-success sd-text-success"><code>VAR_TABLE_RENDERING = False</code></span>
:img-top: assets/xbar-submenu-strandard-rendering.png
:link: assets/xbar-submenu-strandard-rendering.png
```
````

## Location

A copy of the latest stable version of the plugin is
[available on Xbar website](https://xbarapp.com/docs/plugins/Dev/meta_package_manager.7h.py.html)
and
[plugin repository](https://github.com/matryer/xbar-plugins/blob/master/Dev/meta_package_manager.7h.py).

Once `mpm` is installed on your system, it can dynamiccaly be located with the dedicated `--xbar-plugin-path` option:

```shell-session
$ mpm --bar-plugin-path
~/Library/Python/3.9/lib/python/site-packages/meta_package_manager/bar_plugin.py
```

This option is handy for deployment and initial configuration of Xbar/SwiftBar. I personnaly
[use this in my dotfiles](https://github.com/kdeldycke/dotfiles/blob/c04296d29e5f5ce48687f79554b265b3e89d5dbb/install.sh#L230) to symlink the plugin to its latest version:

```shell-session
$ ln -sf "$(mpm --bar-plugin-path)" "${HOME}/Library/Application Support/xbar/plugins/mpm.7h.py"
```

## Python `>=3.8` required

Xbar plugins are self-contained scripts. As such, it needs to be able to run without any extra
dependency, on the pre-installed Python distribution that ships with macOS.

With Python 3.7 being EOL and not receiving any security updates as of 2023-06-27, the plugin **requires Python 3.8 or newer**.

For reference:
- Xbar itself
[requires macOS Catalina or newer (>= 10.15)](https://github.com/matryer/xbar/blame/2d063e0e46a0e427aedef62dc047b0065602cd40/README.md#L9)
- Python 2.x is [deprecated since macOS Catalina (10.15)](https://developer.apple.com/documentation/macos-release-notes/macos-catalina-10_15-release-notes) and has been [removed in macOS Monterey 12.3](https://developer.apple.com/documentation/macos-release-notes/macos-12_3-release-notes#Python)
- It looks like since Monterey (macOS), there is no default Python version installed anymore, and the `python` CLI is a stub that points to the App Store to install Xcode:
   ```shell-session
   $ python3 --version
   xcode-select: note: no developer tools were found at '/Applications/Xcode.app', requesting install. Choose an option in the dialog to download the command line developer tools.
   ```

## Development workflow

Active development of the plugin is happening here, as a side-project of
{command}`mpm` itself.

Releases of the plugin is synchronized with the package. Both share the exact
same version to simplify management. This explain why the plugin could appears
jumping ahead a couple of major/minor versions while providing tiny or no
changes at all.

A release is ready when both the package and the plugin reach a stable state.

If the plugin has been changed between releases, a
[copy of the plugin is pushed](https://github.com/matryer/xbar-plugins/pulls?q=is%3Apr%20%22Meta%20Package%20Manager%22)
under the name `meta_package_manager.7h.py`, to the
[official Xbar plugin repository](https://github.com/matryer/xbar-plugins/blob/master/Dev/meta_package_manager.7h.py).

## Release process

1. [Fork](https://help.github.com/articles/fork-a-repo/) the official
   [Xbar plugin repository](https://github.com/matryer/xbar-plugins).

1. Fetch a local copy of the fork:

   ```shell-session
   $ git clone https://github.com/kdeldycke/xbar-plugins
   $ cd xbar-plugins
   ```

1. Create a new branch and switch to it:

   ```shell-session
   $ git branch "meta-package-manager-v4.13.1"
   $ git checkout "meta-package-manager-v4.13.1"
   ```

1. Replace existing copy of the plugin with the latest tagged version:

   ```shell-session
   $ wget https://raw.githubusercontent.com/kdeldycke/meta-package-manager/v4.13.1/meta_package_manager/bar_plugin.py
   $ mv ./bar_plugin.py ./Dev/meta_package_manager.7h.py
   $ chmod 755 ./Dev/meta_package_manager.7h.py
   ```

1. Commit the new plugin:

   ```shell-session
   $ git add ./Dev/meta_package_manager.7h.py
   $ git commit -m "Upgrade to Meta Package Manager plugin v4.13.1"
   ```

1. Push new branch:

   ```shell-session
   $ git push --set-upstream origin "meta-package-manager-v4.13.1"
   ```

1. [Create a pull-request](https://help.github.com/articles/creating-a-pull-request/)
   in the original repository.
