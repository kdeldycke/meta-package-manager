# Installation

````{admonition} Danger: **Misleading package name**
---
class: danger
---
```{eval-rst}
.. figure:: images/angry-paper-box.png
    :align: right
    :figwidth: 50px
```

There is a *`mpm`* Python module on PyPi that has nothing to do with this project. Avoid it!

The **real package is named `meta-package-manager`**. Only the latter provides the {command}`mpm` CLI
you're looking for.
````

## `pip` install

You can install the latest stable release and its dependencies with a simple `pip`
call:

```shell-session
$ python -m pip install meta-package-manager
```

On some system, due to the Python 2.x to 3.x migration, you'll have to call `python3` directly:

```shell-session
$ python3 -m pip install meta-package-manager
```

Other variations includes:

```shell-session
$ pip install meta-package-manager
```

```shell-session
$ pip3 install meta-package-manager
```

If you have difficulties to use `pip`, see
[`pip`'s own installation instructions](https://pip.pypa.io/en/stable/installation/).

## Run `mpm`

Meta package manager should now be available system-wide:

```shell-session
$ mpm --version
mpm, version 4.13.0
(...)
```

If not, you can directly execute the module from Python:

```shell-session
$ python -m meta_package_manager --version
mpm, version 4.13.0
(...)
```

Or on some systems:

```shell-session
$ python3 -m meta_package_manager --version
mpm, version 4.13.0
(...)
```

## Password prompts and `sudo`

The majority of package managers on Linux requires `sudo` to perform system-wide operations.

On other OSes you'll be prompted to enter your password to install kernel extensions:

```shell-session
$ brew install --cask macfuse
==> Caveats
macfuse requires a kernel extension to work.
If the installation fails, retry after you enable it in:
  System Preferences → Security & Privacy → General

For more information, refer to vendor documentation or this Apple Technical Note:
  https://developer.apple.com/library/content/technotes/tn2459/_index.html

==> Downloading https://github.com/osxfuse/osxfuse/releases/download/macfuse-4.2.5/macfuse-4.2.5.dmg
Already downloaded: /Users/kde/Library/Caches/Homebrew/downloads/d7961d772f16bad95962f1a780b545a5dbb4788ec6e1ec757994bb5296397b1c--macfuse-4.2.5.dmg
==> Installing Cask macfuse
==> Running installer for macfuse; your password may be necessary.
Package installers may write to any location; options such as `--appdir` are ignored.
Password:
```

Both cases are not handled gracefully by `mpm`, which [doesn't support (yet) interactive password](https://github.com/kdeldycke/meta-package-manager/issues/33) management and capture.

## Shell completion

Completion for popular shell
[rely on Click feature](https://click.palletsprojects.com/en/8.1.x/shell-completion/).

`````{tab-set}

````{tab-item} Bash
:sync: bash
Add this to ``~/.bashrc``:

```{code-block} bash
eval "$(_MPM_COMPLETE=bash_source mpm)"
```
````

````{tab-item} Zsh
:sync: zsh
Add this to ``~/.zshrc``:

```{code-block} zsh
eval "$(_MPM_COMPLETE=zsh_source mpm)"
```
````

````{tab-item} Fish
:sync: fish
Add this to ``~/.config/fish/completions/mpm.fish``:

```{code-block} zsh
eval (env _MPM_COMPLETE=fish_source mpm)
```
````

`````

Alternatively, export the generated completion code as a static script to be
executed:

`````{tab-set}

````{tab-item} Bash
:sync: bash
```{code-block} shell-session
$ _MPM_COMPLETE=bash_source mpm > ~/.mpm-complete.bash
```

Then source it from ``~/.bashrc``:

```{code-block} bash
. ~/.mpm-complete.bash
```
````

````{tab-item} Zsh
:sync: zsh
```{code-block} shell-session
$ _MPM_COMPLETE=zsh_source mpm > ~/.mpm-complete.zsh
```

Then source it from ``~/.zshrc``:

```{code-block} zsh
. ~/.mpm.zsh
```
````

````{tab-item} Fish
:sync: fish
```{code-block} fish
_MPM_COMPLETE=fish_source mpm > ~/.config/fish/completions/mpm.fish
```
````

`````

## Python dependencies

FYI, here is a graph of Python package dependencies:

```{image} images/dependencies.png
---
alt: Meta Package Manager dependency graph
align: center
---
```
