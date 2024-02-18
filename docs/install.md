# Installation

```{admonition} Danger: **Misleading package name**
---
class: danger
---
![Angry package](assets/angry-paper-box.png){w=50px align=right}

There is a *`mpm`* Python module on PyPi that has nothing to do with this project. Avoid it!

The **real package is named `meta-package-manager`**. Only the latter provides the {command}`mpm` CLI
you're looking for.
```

## From packages

`mpm` is available on several popular package managers:

![Yo dawg, I herd you like package managers...](assets/yo-dawg-meta-package-manager.jpg){align=center}

`````{tab-set}

````{tab-item} pipx
Easiest way is to [install `pipx`](https://pipx.pypa.io/stable/installation/), then use it to install `mpm`:

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
Meta Package Manager is available as an official [Homebrew](https://brew.sh/) formula, so you just need to:

```{code-block} shell-session
$ brew install meta-package-manager
```
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
`````

## Binaries

Binaries are compiled at each release, so you can skip the installation process above and download the standalone executables directly.

This is the preferred way of testing `mpm` without polluting your machine. They also offer the possibility of running the CLI on older systems not supporting the minimal Python version required by `mpm`.

| Platform          | `x86_64`                                                                                                                         | `arm64` |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------- | --- |
| **Linux** | [Download `mpm-linux-x64.bin`](https://github.com/kdeldycke/meta-package-manager/releases/latest/download/mpm-linux-x64.bin)     | |
| **macOS**         | [Download `mpm-macos-x64.bin`](https://github.com/kdeldycke/meta-package-manager/releases/latest/download/mpm-macos-x64.bin)     | [Download `mpm-macos-arm64.bin`](https://github.com/kdeldycke/meta-package-manager/releases/latest/download/mpm-macos-arm64.bin)  |
| **Windows**       | [Download `mpm-windows-x64.exe`](https://github.com/kdeldycke/meta-package-manager/releases/latest/download/mpm-windows-x64.exe) | |

All links above points to the latest released version of `mpm`.

```{admonition} Older releases
---
class: seealso
---
If you need to test previous versions for regression, compatibility or general troubleshooting, you'll find the old binaries attached as assets to [past releases on GitHub](https://github.com/kdeldycke/meta-package-manager/releases).
```

```{admonition} Development builds
---
class: caution
---
Each commit to the development branch triggers the compilation of binaries. This way you can easily test the bleeding edge version of `mpm` and report any issue.

Look at the [list of latest binary builds](https://github.com/kdeldycke/meta-package-manager/actions/workflows/release.yaml?query=branch%3Amain+is%3Asuccess). Then select the latest `Build & release`/`release.yaml` workflow run and download the binary artifact corresponding to your platform and architecture.
```

````{admonition} ABI targets
---
class: seelalso
---
```{code-block} shell-session
$ file ./mpm*
./mpm-linux-x64.bin:   ELF 64-bit LSB pie executable, x86-64, version 1 (SYSV), dynamically linked, interpreter /lib64/ld-linux-x86-64.so.2, BuildID[sha1]=d0a8ae1ffa469465a836c1505504d1b1c75725b0, for GNU/Linux 3.2.0, stripped
./mpm-macos-arm64.bin: Mach-O 64-bit executable arm64
./mpm-macos-x64.bin:   Mach-O 64-bit executable x86_64
./mpm-windows-x64.exe: PE32+ executable (console) x86-64, for MS Windows
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

````{admonition}
---
class: tip
---
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

```mermaid assets/dependencies.mmd
:align: center
:zoom:
```
