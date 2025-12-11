# {octicon}`download` Installation

```{sidebar}
[![Packaging status](https://repology.org/badge/vertical-allrepos/meta-package-manager.svg)](https://repology.org/project/meta-package-manager/versions)
```

Meta Package Manager is [distributed on PyPi](https://pypi.org/project/meta-package-manager/).

So you can install the latest stable release with your favorite package manager [like `pip`](https://pip.pypa.io):

```{code-block} shell-session
$ pip install meta-package-manager
```

```{danger}
**Misleading package name**

![Angry package](assets/angry-paper-box.png){w=50px align=right}

There is a *`mpm`* Python module on PyPi that has nothing to do with this project. Avoid it!

The **real package is named `meta-package-manager`**. Only the latter provides the {command}`mpm` CLI you're looking for.
```

## Try it now

You can try Meta Package Manager right now in your terminal, without installing any dependency or virtual env [thanks to `uvx`](https://docs.astral.sh/uv/guides/tools/):

`````{tab-set}
````{tab-item} Latest version
```shell-session
$ uvx --from meta-package-manager -- mpm
```
````

````{tab-item} Specific version
```shell-session
$ uvx --from meta-package-manager@5.21.0 -- mpm
```
````

````{tab-item} Development version
```shell-session
$ uvx --from git+https://github.com/kdeldycke/meta-package-manager -- mpm
```
````

````{tab-item} Local version
```shell-session
$ uvx --from file:///Users/me/code/meta-package-manager -- mpm
```
````
`````

This will download `meta-package-manager` (the package), and run `mpm`, the CLI included in the package.

## Installation methods

`mpm` is available on several popular package managers:

![Yo dawg, I herd you like package managers...](assets/yo-dawg-meta-package-manager.jpg){align=center}

`````{tab-set}

````{tab-item} uvx
Easiest way is to [install `uv`](https://docs.astral.sh/uv/getting-started/installation/), then install `meta-package-manager` system-wide, with the [`uv tool`](https://docs.astral.sh/uv/guides/tools/#installing-tools) command:

```{code-block} shell-session
$ uv tool install meta-package-manager
```

Then you can run `mpm` directly:

```{code-block} shell-session
$ mpm --version
```
````

````{tab-item} pipx
[`pipx`](https://pipx.pypa.io/stable/installation/) is a great way to install Python applications globally:

```{code-block} shell-session
$ pipx install meta-package-manager
```
````

````{tab-item} pip
You can install the latest stable release and its dependencies with a simple `pip` call:

```{code-block} shell-session
$ python -m pip install meta-package-manager
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
Meta Package Manager is [available as an Homebrew formula](https://formulae.brew.sh/formula/meta-package-manager), so you just need to:

```{code-block} shell-session
$ brew install meta-package-manager
```
````

````{tab-item} Scoop
Meta Package Manager is available in the `main` repository of [Scoop](https://scoop.sh), so you just need to:

```{code-block} pwsh-session
> scoop install main/meta-package-manager
```
````

````{tab-item} Arch Linux
An `mpm` package is [available on AUR](https://aur.archlinux.org/packages/meta-package-manager) and can be installed with any AUR helper:

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
`````

## Binaries

Binaries are compiled at each release, so you can skip the installation process above and download the standalone executables directly.

This is the preferred way of testing `mpm` without polluting your machine. They also offer the possibility of running the CLI on older systems not supporting the minimal Python version required by `mpm`.

| Platform    | `arm64`                                                                                                                              | `x86_64`                                                                                                                         |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| **Linux**   | [Download `mpm-linux-arm64.bin`](https://github.com/kdeldycke/meta-package-manager/releases/latest/download/mpm-linux-arm64.bin)     | [Download `mpm-linux-x64.bin`](https://github.com/kdeldycke/meta-package-manager/releases/latest/download/mpm-linux-x64.bin)     |
| **macOS**   | [Download `mpm-macos-arm64.bin`](https://github.com/kdeldycke/meta-package-manager/releases/latest/download/mpm-macos-arm64.bin)     | [Download `mpm-macos-x64.bin`](https://github.com/kdeldycke/meta-package-manager/releases/latest/download/mpm-macos-x64.bin)     |
| **Windows** | [Download `mpm-windows-arm64.exe`](https://github.com/kdeldycke/meta-package-manager/releases/latest/download/mpm-windows-arm64.exe) | [Download `mpm-windows-x64.exe`](https://github.com/kdeldycke/meta-package-manager/releases/latest/download/mpm-windows-x64.exe) |

All links above points to the latest released version of `mpm`.

```{seealso}
If you need to test previous versions for regression, compatibility or general troubleshooting, you'll find the old binaries attached as assets to [past releases on GitHub](https://github.com/kdeldycke/meta-package-manager/releases).
```

```{caution}
Each commit to the development branch triggers the compilation of binaries. This way you can easily test the bleeding edge version of `mpm` and report any issue.

Look at the [list of latest binary builds](https://github.com/kdeldycke/meta-package-manager/actions/workflows/release.yaml?query=branch%3Amain+is%3Asuccess). Then select the latest `Build & release`/`release.yaml` workflow run and download the binary artifact corresponding to your platform and architecture.
```

````{note} ABI targets
```{code-block} shell-session
$ file ./mpm*
./mpm-linux-arm64.bin:   ELF 64-bit LSB pie executable, ARM aarch64, version 1 (SYSV), dynamically linked, interpreter /lib/ld-linux-aarch64.so.1, BuildID[sha1]=520bfc6f2bb21f48ad568e46752888236552b26a, for GNU/Linux 3.7.0, stripped
./mpm-linux-x64.bin:     ELF 64-bit LSB pie executable, x86-64, version 1 (SYSV), dynamically linked, interpreter /lib64/ld-linux-x86-64.so.2, BuildID[sha1]=56ba24bccfa917e6ce9009223e4e83924f616d46, for GNU/Linux 3.2.0, stripped
./mpm-macos-arm64.bin:   Mach-O 64-bit executable arm64
./mpm-macos-x64.bin:     Mach-O 64-bit executable x86_64
./mpm-windows-arm64.exe: PE32+ executable (console) Aarch64, for MS Windows
./mpm-windows-x64.exe:   PE32+ executable (console) x86-64, for MS Windows
```
````

## Self-bootstrapping

In a funny twist, `mpm` can be installed with itself.

Which means there is a way to bootstrap its deployment on an unknown system. Just [download the binary](#binaries) corresponding to your platform and architecture:

```{code-block} shell-session
$ curl --fail --remote-name https://github.com/kdeldycke/meta-package-manager/releases/latest/download/mpm-macos-x64.bin
################################################### 100.0%
```

```{code-block} shell-session
$ file ./mpm-macos-x64.bin
./mpm-macos-x64.bin: Mach-O 64-bit executable x86_64
```

```{code-block} shell-session
$ chmod +x ./mpm-macos-x64.bin
```

```{code-block} shell-session
$ ./mpm-macos-x64.bin --version
mpm, version 5.7.0
```

Then let `mpm` discovers which package managers are available on your machine and choose the one providing a path to `mpm` installation:

```{code-block} shell-session
$ ./mpm-macos-x64.bin install meta-package-manager
warning: Skip unavailable cargo manager.
warning: Skip unavailable steamcmd manager.
Installation priority: brew > cask > composer > gem > mas > npm > pip > pipx > vscode > yarn
warning: No meta-package-manager package found on brew.
warning: No meta-package-manager package found on cask.
warning: No meta-package-manager package found on composer.
warning: No meta-package-manager package found on gem.
warning: No meta-package-manager package found on mas.
warning: No meta-package-manager package found on npm.
warning: pip does not implement search operation.
meta-package-manager existence unconfirmed, try to directly install it...
Install meta-package-manager package with pip...
Collecting meta-package-manager
  Downloading meta_package_manager-5.11.1-py3-none-any.whl (161 kB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 161.5/161.5 kB 494.7 kB/s eta 0:00:00
(...)
Installing collected packages: (...) meta-package-manager
Successfully installed (...) meta-package-manager-5.11.1
```

And now you can remove the local binary and enjoy the system-wide `mpm` that was installed by itself:

```{code-block} shell-session
$ rm -f ./mpm-macos-x64.bin
```

```{code-block} shell-session
$ which mpm
/opt/homebrew/bin/mpm
```

```{code-block} shell-session
$ mpm --version
mpm, version 5.11.1
```

````{tip}
At this moment, `mpm` can be installed with itself via these managers:

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

## Python module usage

Meta Package Manager should now be available system-wide:

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
$ sudo python -m pip install meta-package-manager
(...)
$ sudo python -m meta_package_manager upgrade
(...)
```

## Shell completion

Completion for popular shell [rely on Click feature](https://click.palletsprojects.com/en/stable/shell-completion/).

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

## Main dependencies

This is a graph of the default, main dependencies of the Python package:

```mermaid assets/dependencies.mmd
:align: center
```
