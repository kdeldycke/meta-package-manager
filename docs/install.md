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

`````{tab-set}

````{tab-item} pipx
Easiest way is to [install `pipx`](https://pypa.github.io/pipx/installation/), then use it to install `mpm`:

```{code-block} shell-session
$ pipx install meta-package-manager
```

```{note}
`pipx` is to `pip` what `npx` is to `npm`: a clean way to install and run Python applications in isolated environments.
```
````

````{tab-item} pip
You can install the latest stable release and its dependencies with a simple `pip`
call:

```{code-block} shell-session
$ python -m pip install meta-package-manager
```

On some system, due to the Python 2.x to 3.x migration, you'll have to call `python3` directly:

```{code-block} shell-session
$ python3 -m pip install meta-package-manager
```

Other variations includes:

```{code-block} shell-session
$ pip install meta-package-manager
```

```{code-block} shell-session
$ pip3 install meta-package-manager
```

If you have difficulties to use `pip`, see
[`pip`'s own installation instructions](https://pip.pypa.io/en/stable/installation/).
````

````{tab-item} brew
An `mpm` formula has been contributed by [@Hasnep](https://github.com/Hasnep) and is [available at `hasnep/tap/meta-package-manager`](https://github.com/Hasnep/homebrew-tap/blob/main/Formula/meta-package-manager.rb):

```{code-block} shell-session
$ brew install hasnep/tap/meta-package-manager
```

```{admonition} Broken Homebrew
:class: tip

If for any reason `brew` gets broken by this external repository, you can easily fix it running:

```{code-block} shell-session
$ brew untap hasnep/tap
$ brew install hasnep/tap/meta-package-manager
```
````

````{tab-item} macOS
A [standalone `mpm.bin` executable](https://github.com/kdeldycke/meta-package-manager/releases/latest) for `x86_64` is available on macOS, so you can run it without a fuss.
````

````{tab-item} Arch Linux
An `mpm` package has been contributed by [@autinerd](https://github.com/autinerd) and is [available on AUR](https://aur.archlinux.org/packages/meta-package-manager) and can be installed with any AUR helper:

```{code-block} shell-session
$ pacaur -S meta-package-manager
```

```{code-block} shell-session
$ pacman -S meta-package-manager
```

```{code-block} shell-session
$ paru -S meta-package-manager
```

```{code-block} shell-session
$ yay -S meta-package-manager
```
````

````{tab-item} Linux
A [standalone `mpm.bin` executable](https://github.com/kdeldycke/meta-package-manager/releases/latest) for `x86_64` is available on Linux, so you can run it without a fuss.
````

````{tab-item} Windows
## Executable

A [standalone `mpm.exe` executable](https://github.com/kdeldycke/meta-package-manager/releases/latest) for `x86_64` is available on Windows, so you can run it without a fuss.

## From sources

You need is a working Python on your machine. Here is for example how to install it with Chocolatey:

1. [Install chocolatey](https://chocolatey.org/install#install-step2)
1. Install Python via chocolatey:
    ```{code-block} shell-session
    $ choco install python -y
    ```
1. Then follow the `mpm` installation instruction in `pipx` or `pip` tabs.
````

````{tab-item} mpm
In a funny twist, `mpm` can be installed with itself:

```{code-block} shell-session
$ mpm --brew install meta-package-manager
```

```{code-block} shell-session
$ mpm --pacaur install meta-package-manager
```

```{code-block} shell-session
$ mpm --pacman install meta-package-manager
```

```{code-block} shell-session
$ mpm --paru install meta-package-manager
```

```{code-block} shell-session
$ mpm --pip  install meta-package-manager
```

```{code-block} shell-session
$ mpm --pipx install meta-package-manager
```

```{code-block} shell-session
$ mpm --yay  install meta-package-manager
```
````
`````

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

A workaround on Linux is to install `mpm` with `sudo`, so you'll be able to invoke it with `sudo` too:

```shell-session
$ sudo python3 -m pip install meta-package-manager
(...)
$ sudo python3 -m meta_package_manager upgrade
(...)
```

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
