# {octicon}`download` Installation

```{sidebar}
[![Packaging status](https://repology.org/badge/vertical-allrepos/meta-package-manager.svg)](https://repology.org/project/meta-package-manager/versions)
```

Meta Package Manager is [distributed on PyPI](https://pypi.org/project/meta-package-manager/).

So you can install the latest stable release [with `uv`](https://docs.astral.sh/uv/):

```{code-block} shell-session
$ uv tool install meta-package-manager
```

```{danger}
**Misleading package name**

![Angry package](assets/angry-paper-box.png){w=50px align=right}

There is a *`mpm`* Python module on PyPI that has nothing to do with this project. Avoid it!

The **real package is named `meta-package-manager`**. Only the latter provides the {command}`mpm` CLI you're looking for.
```

## Try it now

You can try Meta Package Manager right now in your terminal, without installing any dependency or virtual env [thanks to `uvx`](https://docs.astral.sh/uv/guides/tools/):

``````{tab-set}
`````{tab-item} Latest version
```shell-session
$ uvx meta-package-manager
Installed 21 packages in 42ms
Usage: mpm [OPTIONS] COMMAND [ARGS]...
```
`````

`````{tab-item} Specific version
```shell-session
$ uvx meta-package-manager@6.6.0
Installed 21 packages in 42ms
Usage: mpm [OPTIONS] COMMAND [ARGS]...
```
`````

`````{tab-item} Development version
```shell-session
$ uvx --from git+https://github.com/kdeldycke/meta-package-manager -- mpm
```
`````

`````{tab-item} Local version
```shell-session
$ uvx --from file:///Users/me/code/meta-package-manager -- mpm
```
`````
``````

This will download `meta-package-manager` (the package), and run `mpm`, the CLI included in the package.

## Try the library

You can also try the library itself in an interactive Python shell without installing anything on your system:

```{code-block} shell-session
$ uvx --with meta-package-manager python
Installed 21 packages in 42ms
Python 3.13.2 (main, Feb  4 2025, 14:51:09) [Clang 16.0.0 (clang-1600.0.26.6)] on darwin
Type "help", "copyright", "credits" or "license" for more information.
>>> from meta_package_manager.pool import pool
>>> list(pool['brew'].installed)
[...]
>>>
```

## Installation methods

<!-- Keep in sync with .github/workflows/tests-install.yaml -->

<!-- Tabs are sorted by popularity: uv first, then by estimated user base. -->

`mpm` is available on several popular package managers:

![Yo dawg, I herd you like package managers...](assets/yo-dawg-meta-package-manager.jpg){align=center}

``````{tab-set}

`````{tab-item} uv
Easiest way is to [install `uv`](https://docs.astral.sh/uv/getting-started/installation/), then install `meta-package-manager` system-wide with the [`uv tool`](https://docs.astral.sh/uv/guides/tools/#installing-tools) command:

```{code-block} shell-session
$ uv tool install meta-package-manager
```

Then you can run `mpm` directly:

```{code-block} shell-session
$ mpm --version
```

To use `mpm` as a library in your project instead:

```{code-block} shell-session
$ uv add meta-package-manager
```
`````

`````{tab-item} pip
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
`````

`````{tab-item} pipx
[`pipx`](https://pipx.pypa.io/latest/install-pipx/) is a great way to install Python applications globally:

```{code-block} shell-session
$ pipx install meta-package-manager
```
`````

`````{tab-item} Homebrew
Meta Package Manager is [available as a Homebrew formula](https://formulae.brew.sh/formula/meta-package-manager), so you just need to:

```{code-block} shell-session
$ brew install meta-package-manager
```

````{tip}
[ZeroBrew](https://github.com/lucasgelfond/zerobrew) is a fast, Homebrew-compatible package manager written in Rust. It consumes the same formula and installs `mpm` with:

```{code-block} shell-session
$ zb install meta-package-manager
```
````
`````

`````{tab-item} MacPorts
While the port is pending review, build and install from [the Portfile overlay maintained in the repository](https://github.com/kdeldycke/meta-package-manager/tree/main/packaging/macports):

```{code-block} shell-session
$ git clone https://github.com/kdeldycke/meta-package-manager.git
$ portindex ./meta-package-manager/packaging/macports
```

Then register the overlay as your first ports tree, by adding its absolute path at the top of `/opt/local/etc/macports/sources.conf`:

```{code-block} text
file:///path/to/meta-package-manager/packaging/macports
```

Finally:

```{code-block} shell-session
$ sudo port install meta-package-manager
```

The overlay carries the 5 dependency ports missing from the official tree (`py-click-extra`, `py-cloup`, `py-deepmerge`, `py-extra-platforms`, `py-packageurl-python`), plus a `py-boltons` version bump.

````{admonition} Help land it in MacPorts
:class: important
The port is pending review at [macports/macports-ports#33609](https://github.com/macports/macports-ports/pull/33609). Once merged, installation will be a one-liner:

```{code-block} shell-session
$ sudo port install meta-package-manager
```

You can help move it forward by showing your support on [the pull request](https://github.com/macports/macports-ports/pull/33609).
````
`````

`````{tab-item} Scoop
Meta Package Manager is available in the `main` repository of [Scoop](https://scoop.sh), so you just need to:

```{code-block} pwsh-session
> scoop install main/meta-package-manager
```
`````

`````{tab-item} Chocolatey
Build and install from [the specs maintained in the repository](https://github.com/kdeldycke/meta-package-manager/tree/main/packaging/choco/meta-package-manager):

```{code-block} pwsh-session
> git clone https://github.com/kdeldycke/meta-package-manager.git
> cd meta-package-manager\packaging\choco\meta-package-manager
> choco pack
> choco install meta-package-manager --source .
```

````{admonition} Not available on the Chocolatey community repository
:class: warning
[Submission `6.4.2`](https://community.chocolatey.org/packages/meta-package-manager/6.4.2) was rejected: the Windows x64 binary trips too many antivirus engines on VirusTotal for community-repository moderation to clear it. See [Antivirus false positives](#antivirus-false-positives) below for the full background, and please [report the detection to your antivirus vendor](#antivirus-false-positives) if it affects you: enough reports may eventually bring the detection count back under Chocolatey's cutoff.
````
`````

`````{tab-item} Nix
Build and install from [the definition maintained in the repository](https://github.com/kdeldycke/meta-package-manager/tree/main/packaging/nix):

```{code-block} shell-session
$ git clone https://github.com/kdeldycke/meta-package-manager.git
$ nix-env -f ./meta-package-manager/packaging/nix -i
```

On flake-enabled systems:

```{code-block} shell-session
$ nix run github:kdeldycke/meta-package-manager?dir=packaging/nix -- --version
```

````{admonition} Help land it in nixpkgs
:class: important
The nixpkgs package is pending review at [NixOS/nixpkgs#506145](https://github.com/NixOS/nixpkgs/pull/506145). Once merged, installation will be a one-liner:

```{code-block} shell-session
$ nix-env --install --attr nixpkgs.meta-package-manager
```

Or, without installing:

```{code-block} shell-session
$ nix-shell -p meta-package-manager --run "mpm --version"
```

On flake-enabled systems:

```{code-block} shell-session
$ nix run nixpkgs#meta-package-manager -- --version
```

You can help move it forward by showing your support on [the pull request](https://github.com/NixOS/nixpkgs/pull/506145).
````
`````

`````{tab-item} Guix
Meta Package Manager is [available in GNU Guix](https://packages.guix.gnu.org/packages/meta-package-manager/), so you just need to:

```{code-block} shell-session
$ guix install meta-package-manager
```

```{tip}
The package [landed in Guix on 2026-06-28](https://codeberg.org/guix/guix/pulls/8047). If `guix install` cannot find it yet, refresh your channels first with `guix pull`.
```

To build the bleeding-edge version instead, install from [the definition maintained in the repository](https://github.com/kdeldycke/meta-package-manager/tree/main/packaging/guix):

```{code-block} shell-session
$ git clone https://github.com/kdeldycke/meta-package-manager.git
$ guix install --load-path=./meta-package-manager/packaging/guix meta-package-manager
```
`````

`````{tab-item} Alpine Linux
Build and install from [the APKBUILD overlay maintained in the repository](https://github.com/kdeldycke/meta-package-manager/tree/main/packaging/alpine). It targets Alpine edge, the only branch shipping `py3-uv-build` (`mpm`'s build backend) and `py3-boltons` >= `25`.

As a member of the `abuild` group, with a signing key set up:

```{code-block} shell-session
$ doas apk add alpine-sdk
$ abuild-keygen --append --install -n
$ git clone https://github.com/kdeldycke/meta-package-manager.git
$ cd ./meta-package-manager/packaging/alpine
$ abuild -C ./py3-cloup -r
$ abuild -C ./py3-extra-platforms -r
$ abuild -C ./py3-packageurl -r
$ abuild -C ./py3-click-extra -r
$ abuild -C ./meta-package-manager -r
$ doas apk add --repository ~/.local/share/abuild/alpine meta-package-manager
```

Each `abuild` run drops its packages in `~/.local/share/abuild/alpine` (abuild's default `REPODEST`), where the next builds and the final `apk add` pick them up.

The overlay carries the 4 dependency packages missing from the official aports tree (`py3-click-extra`, `py3-cloup`, `py3-extra-platforms`, `py3-packageurl`).
`````

`````{tab-item} Void Linux
While the package is pending upstream review, build and install it from my fork's [`mpm` branch](https://github.com/kdeldycke/void-packages/tree/mpm):

```{code-block} shell-session
$ git clone --depth 1 --branch mpm https://github.com/kdeldycke/void-packages.git
$ cd ./void-packages
$ ./xbps-src binary-bootstrap
$ ./xbps-src pkg mpm
$ sudo xbps-install --repository=./hostdir/binpkgs/mpm mpm
```

`./xbps-src pkg mpm` cascades through and builds the 16 dependency packages introduced by the fork (15 new Python packages plus an in-place bump of `python3-boltons` from `20.2.1` to `25.0.0` for Python 3.14 compatibility).

````{admonition} Help land it in void-packages
:class: important
The Void package is pending review at [void-linux/void-packages#60532](https://github.com/void-linux/void-packages/pull/60532). Once merged, installation will be a one-liner:

```{code-block} shell-session
$ xbps-install --sync mpm
```

You can help move it forward by showing your support on [the pull request](https://github.com/void-linux/void-packages/pull/60532).
````
`````

`````{tab-item} Arch Linux
An `mpm` package is [available on AUR](https://aur.archlinux.org/packages/meta-package-manager) and can be installed with any AUR helper:

```{code-block} shell-session
$ yay -S meta-package-manager
```

```{code-block} shell-session
$ paru -S meta-package-manager
```

```{code-block} shell-session
$ pacaur -S meta-package-manager
```
`````

`````{tab-item} Stew
[Stew](https://github.com/marwanhawari/stew) installs pre-compiled binaries from GitHub Releases:

```{code-block} shell-session
$ stew install kdeldycke/meta-package-manager
```
`````

``````

## Binaries

Binaries are compiled at each release, so you can skip the installation process above and download the standalone executables directly.

This is the preferred way of testing `mpm` without polluting your machine. They also offer the possibility of running the CLI on older systems not supporting the minimal Python version required by `mpm`.

```{python:render}
from docs_update import binaries_download_table

print(binaries_download_table())
```

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
$ file ./meta-package-manager-*
./meta-package-manager-7.3.0-linux-arm64.bin:   ELF 64-bit LSB pie executable, ARM aarch64, version 1 (SYSV), dynamically linked, interpreter /lib/ld-linux-aarch64.so.1, BuildID[sha1]=520bfc6f2bb21f48ad568e46752888236552b26a, for GNU/Linux 3.7.0, stripped
./meta-package-manager-7.3.0-linux-x64.bin:     ELF 64-bit LSB pie executable, x86-64, version 1 (SYSV), dynamically linked, interpreter /lib64/ld-linux-x86-64.so.2, BuildID[sha1]=56ba24bccfa917e6ce9009223e4e83924f616d46, for GNU/Linux 3.2.0, stripped
./meta-package-manager-7.3.0-macos-arm64.bin:   Mach-O 64-bit executable arm64
./meta-package-manager-7.3.0-macos-x64.bin:     Mach-O 64-bit executable x86_64
./meta-package-manager-7.3.0-windows-arm64.exe: PE32+ executable (console) Aarch64, for MS Windows
./meta-package-manager-7.3.0-windows-x64.exe:   PE32+ executable (console) x86-64, for MS Windows
```
````

(antivirus-false-positives)=

```{important} Antivirus false positives
The Windows binaries (and to a lesser extent the macOS ARM64 ones, plus anything downstream that bundles them like the Chocolatey package) are flagged by heuristic and ML-based antivirus engines. These are false positives caused by the [Nuitka](https://nuitka.net) `--onefile` packaging pattern, not by anything `mpm` does. Engineering background, per-release detection data, and long-term mitigations are documented on the [binaries catalog](binaries.md#antivirus-false-positives-on-windows-binaries).

**If your antivirus quarantines an `mpm` binary:**

1. Verify the binary you downloaded with the [attestation procedure below](#release-verification). It cryptographically proves the artifact came from this repository's release pipeline.
2. Submit a false-positive report to your antivirus vendor with the verified binary. The [priority vendor list on the binaries catalog](binaries.md#submitting-false-positive-reports) covers the engines responsible for most detections, and [VirusTotal's vendor directory](https://docs.virustotal.com/docs/false-positive-contacts) covers the rest.

The more independent reports a vendor receives, the more likely a detection gets reclassified, and that is the only practical path back to a working Chocolatey community-repository submission.
```

## Release verification

All release artifacts (Python packages and compiled binaries) are signed with [GitHub Artifact Attestations](https://docs.github.com/en/actions/security-guides/using-artifact-attestations-to-establish-provenance-for-builds) providing [SLSA v1 provenance](https://slsa.dev/spec/v1.0/). You can verify any downloaded artifact with the [GitHub CLI](https://cli.github.com):

```{code-block} shell-session
$ gh attestation verify ./meta-package-manager-7.3.0-macos-arm64.bin --repo kdeldycke/meta-package-manager --signer-repo kdeldycke/repomatic
Loaded digest sha256:... for file://meta-package-manager-7.3.0-macos-arm64.bin
Loaded 1 attestation from GitHub API
✓ Verification succeeded!
```

```{important}
The `--signer-repo kdeldycke/repomatic` flag is required because the release workflow runs as a [reusable workflow](https://docs.github.com/en/actions/sharing-automations/reusing-workflows) from [`kdeldycke/repomatic`](https://github.com/kdeldycke/repomatic). The signing certificate references that repository, not `kdeldycke/meta-package-manager`. Without this flag, verification fails.
```

For Python packages from PyPI:

```{code-block} shell-session
$ gh attestation verify ./meta_package_manager-6.2.1-py3-none-any.whl --repo kdeldycke/meta-package-manager --signer-repo kdeldycke/repomatic
```

Attestation bundles are also attached to each [GitHub release](https://github.com/kdeldycke/meta-package-manager/releases) for offline verification.

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
$ mpm --guix install meta-package-manager
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

```{code-block} pwsh-session
> mpm --choco install meta-package-manager
```

```{code-block} shell-session
$ mpm --pip  install meta-package-manager
```

```{code-block} shell-session
$ mpm --pipx install meta-package-manager
```

```{code-block} pwsh-session
> mpm --scoop install meta-package-manager
```

```{code-block} shell-session
$ mpm --stew install kdeldycke/meta-package-manager
```

```{code-block} shell-session
$ mpm --uvx install meta-package-manager
```

```{code-block} shell-session
$ mpm --yay  install meta-package-manager
```

```{code-block} shell-session
$ mpm --zerobrew install meta-package-manager
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

## Python compatibility

The table below shows which Python versions each `mpm` release range supports. For `5.17.0` and later, support comes from the `Programming Language :: Python :: 3.X` classifiers in `pyproject.toml`. For earlier releases, the floor comes from the `requires-python` (or Poetry `python = "..."` for older tags) or `python_requires` (`setup.py`) declaration, capped at the latest Python released within the range. Releases before `1.8.0` did not declare Python version support and are not represented. The table is regenerated from the release tags by repomatic's `update-docs` job, through click-extra's [`matrix` mechanism](https://kdeldycke.github.io/click-extra/sphinx.html#the-matrix-directive):

<!-- matrix python package=mpm -->

| `mpm`               | Released   | `2.7` | `3.3` | `3.4` | `3.5` | `3.6` | `3.7` | `3.8` | `3.9` | `3.10` | `3.11` | `3.12` | `3.13` | `3.14` |
| :------------------ | :--------- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :----: | :----: | :----: | :----: | :----: |
| `6.0.x` → `7.x`     | 2025-12-08 |  ❌   |  ❌   |  ❌   |  ❌   |  ❌   |  ❌   |  ❌   |  ❌   |   ✅   |   ✅   |   ✅   |   ✅   |   ✅   |
| `5.21.0`            | 2025-05-28 |  ❌   |  ❌   |  ❌   |  ❌   |  ❌   |  ❌   |  ❌   |  ❌   |   ❌   |   ✅   |   ✅   |   ✅   |   ❌   |
| `5.19.x` → `5.20.x` | 2024-11-13 |  ❌   |  ❌   |  ❌   |  ❌   |  ❌   |  ❌   |  ❌   |  ❌   |   ✅   |   ✅   |   ✅   |   ✅   |   ❌   |
| `5.17.x` → `5.18.x` | 2024-07-07 |  ❌   |  ❌   |  ❌   |  ❌   |  ❌   |  ❌   |  ❌   |  ✅   |   ✅   |   ✅   |   ✅   |   ❌   |   ❌   |
| `5.14.x` → `5.16.x` | 2024-01-12 |  ❌   |  ❌   |  ❌   |  ❌   |  ❌   |  ❌   |  ✅   |  ✅   |   ✅   |   ✅   |   ✅   |   ❌   |   ❌   |
| `3.2.x` → `5.13.x`  | 2020-05-31 |  ❌   |  ❌   |  ❌   |  ❌   |  ❌   |  ✅   |  ✅   |  ✅   |   ✅   |   ✅   |   ✅   |   ❌   |   ❌   |
| `2.9.x` → `3.1.x`   | 2020-03-18 |  ❌   |  ❌   |  ❌   |  ❌   |  ✅   |  ✅   |  ✅   |  ❌   |   ❌   |   ❌   |   ❌   |   ❌   |   ❌   |
| `2.5.x` → `2.8.x`   | 2017-03-01 |  ✅   |  ❌   |  ✅   |  ✅   |  ✅   |  ✅   |  ✅   |  ❌   |   ❌   |   ❌   |   ❌   |   ❌   |   ❌   |
| `2.1.x` → `2.4.x`   | 2016-12-17 |  ✅   |  ✅   |  ✅   |  ✅   |  ✅   |  ❌   |  ❌   |  ❌   |   ❌   |   ❌   |   ❌   |   ❌   |   ❌   |
| `1.8.x` → `2.1.x`   | 2016-08-22 |  ✅   |  ✅   |  ✅   |  ✅   |  ❌   |  ❌   |  ❌   |  ❌   |   ❌   |   ❌   |   ❌   |   ❌   |   ❌   |

<!-- matrix-end -->

## click-extra compatibility

`mpm` builds its CLI on [click-extra](https://github.com/kdeldycke/click-extra), and the two evolve in lockstep: most `mpm` releases raise their click-extra floor to pick up features and fixes. The table below shows which click-extra versions each `mpm` release range accepts at install time, derived from the click-extra requirement specifier across release tags. Columns are minor-grouped where the specifiers only distinguish minors, and split per patch where a floor pins a specific patch; the right edge is the click-extra version currently resolved in `uv.lock`. Rows start at `6.0.0` to keep the column set readable, and the table is regenerated by the same [`matrix` mechanism](https://kdeldycke.github.io/click-extra/sphinx.html#the-matrix-directive) as the Python one:

<!-- matrix click-extra package=mpm version-floor=6.0.0 show-spec -->

| `mpm`             | Released   | Spec       | `7.2` | `7.5.0` | `7.5.1` | `7.6.0` | `7.6.2` | `7.7` | `7.11` | `7.15` | `7.16.0` | `7.16.1` | `7.19` | `8.1.0` | `8.1.1` | `8.2` | `8.3` | `8.4` |
| :---------------- | :--------- | :--------- | :---: | :-----: | :-----: | :-----: | :-----: | :---: | :----: | :----: | :------: | :------: | :----: | :-----: | :-----: | :---: | :---: | :---: |
| `7.3.0`           | 2026-07-17 | `>=8.4`    |  ❌   |   ❌    |   ❌    |   ❌    |   ❌    |  ❌   |   ❌   |   ❌   |    ❌    |    ❌    |   ❌   |   ❌    |   ❌    |  ❌   |  ❌   |  ✅   |
| `7.2.0`           | 2026-07-09 | `>=8.3`    |  ❌   |   ❌    |   ❌    |   ❌    |   ❌    |  ❌   |   ❌   |   ❌   |    ❌    |    ❌    |   ❌   |   ❌    |   ❌    |  ❌   |  ✅   |  ✅   |
| `7.1.0`           | 2026-07-07 | `>=8.2`    |  ❌   |   ❌    |   ❌    |   ❌    |   ❌    |  ❌   |   ❌   |   ❌   |    ❌    |    ❌    |   ❌   |   ❌    |   ❌    |  ✅   |  ✅   |  ✅   |
| `7.0.x`           | 2026-06-26 | `>=8.1.1`  |  ❌   |   ❌    |   ❌    |   ❌    |   ❌    |  ❌   |   ❌   |   ❌   |    ❌    |    ❌    |   ❌   |   ❌    |   ✅    |  ✅   |  ✅   |  ✅   |
| `6.6.0`           | 2026-06-17 | `>=7.19`   |  ❌   |   ❌    |   ❌    |   ❌    |   ❌    |  ❌   |   ❌   |   ❌   |    ❌    |    ❌    |   ✅   |   ✅    |   ✅    |  ✅   |  ✅   |  ✅   |
| `6.5.x`           | 2026-05-25 | `>=7.16.1` |  ❌   |   ❌    |   ❌    |   ❌    |   ❌    |  ❌   |   ❌   |   ❌   |    ❌    |    ✅    |   ✅   |   ✅    |   ✅    |  ✅   |  ✅   |  ✅   |
| `6.4.x`           | 2026-05-04 | `>=7.15`   |  ❌   |   ❌    |   ❌    |   ❌    |   ❌    |  ❌   |   ❌   |   ✅   |    ✅    |    ✅    |   ✅   |   ✅    |   ✅    |  ✅   |  ✅   |  ✅   |
| `6.4.0`           | 2026-04-27 | `>=7.11`   |  ❌   |   ❌    |   ❌    |   ❌    |   ❌    |  ❌   |   ✅   |   ✅   |    ✅    |    ✅    |   ✅   |   ✅    |   ✅    |  ✅   |  ✅   |  ✅   |
| `6.2.x` → `6.3.x` | 2026-03-26 | `>=7.7.0`  |  ❌   |   ❌    |   ❌    |   ❌    |   ❌    |  ✅   |   ✅   |   ✅   |    ✅    |    ✅    |   ✅   |   ✅    |   ✅    |  ✅   |  ✅   |  ✅   |
| `6.2.0`           | 2026-03-25 | `>=7.6.2`  |  ❌   |   ❌    |   ❌    |   ❌    |   ✅    |  ✅   |   ✅   |   ✅   |    ✅    |    ✅    |   ✅   |   ✅    |   ✅    |  ✅   |  ✅   |  ✅   |
| `6.1.1`           | 2026-02-05 | `>=7.5.1`  |  ❌   |   ❌    |   ✅    |   ✅    |   ✅    |  ✅   |   ✅   |   ✅   |    ✅    |    ✅    |   ✅   |   ✅    |   ✅    |  ✅   |  ✅   |  ✅   |
| `6.0.x` → `6.1.x` | 2025-12-08 | `>=7.2.0`  |  ✅   |   ✅    |   ✅    |   ✅    |   ✅    |  ✅   |   ✅   |   ✅   |    ✅    |    ✅    |   ✅   |   ✅    |   ✅    |  ✅   |  ✅   |  ✅   |

<!-- matrix-end -->

## Shell completion

Completion for popular shell [rely on Click feature](https://click.palletsprojects.com/en/stable/shell-completion/).

``````{tab-set}

`````{tab-item} Bash
:sync: bash
Add this to ``~/.bashrc``:

```{code-block} bash
eval "$(_MPM_COMPLETE=bash_source mpm)"
```
`````

`````{tab-item} Zsh
:sync: zsh
Add this to ``~/.zshrc``:

```{code-block} zsh
eval "$(_MPM_COMPLETE=zsh_source mpm)"
```
`````

`````{tab-item} Fish
:sync: fish
Add this to ``~/.config/fish/completions/mpm.fish``:

```{code-block} zsh
eval (env _MPM_COMPLETE=fish_source mpm)
```
`````

``````

Alternatively, export the generated completion code as a static script to be
executed:

``````{tab-set}

`````{tab-item} Bash
:sync: bash
```{code-block} shell-session
$ _MPM_COMPLETE=bash_source mpm > ~/.mpm-complete.bash
```

Then source it from ``~/.bashrc``:

```{code-block} bash
. ~/.mpm-complete.bash
```
`````

`````{tab-item} Zsh
:sync: zsh
```{code-block} shell-session
$ _MPM_COMPLETE=zsh_source mpm > ~/.mpm-complete.zsh
```

Then source it from ``~/.zshrc``:

```{code-block} zsh
. ~/.mpm.zsh
```
`````

`````{tab-item} Fish
:sync: fish
```{code-block} fish
_MPM_COMPLETE=fish_source mpm > ~/.config/fish/completions/mpm.fish
```
`````

``````

For broader shell coverage than Click's Bash, Zsh and Fish support, mpm's command tree can be exported to [Carapace](https://carapace.sh), a multi-shell completion engine that drives identical completions across Bash, Zsh, Fish, Nushell, PowerShell, Elvish and more from a single spec. Generate and install the spec with [click-extra](https://kdeldycke.github.io/click-extra/carapace.html)'s `wrap` command:

```{code-block} shell-session
$ uvx --from "click-extra[carapace]" --with meta-package-manager click-extra wrap --carapace --install meta_package_manager.cli:mpm
```

This writes the spec to `~/.config/carapace/specs/mpm.yaml`, which [Carapace](https://carapace.sh) loads once it is installed and hooked into your shell. Re-run the command after upgrading mpm to refresh the spec.

## Man pages

`mpm` exposes a `--man` option on every (sub)command that prints the corresponding roff page to stdout. Pipe it through `man --local-file -` to render it:

```{code-block} shell-session
$ mpm --man | man --local-file -
```

```{code-block} shell-session
$ mpm install --man | man --local-file -
```

The full command tree is also pre-rendered as static `.1` files:

- Bundled as `mpm-manpages.tar.gz` on every [GitHub release](https://github.com/kdeldycke/meta-package-manager/releases). Download, extract, and copy to `${MANPATH%%:*}/man1/` (typically `/usr/local/share/man/man1/`).
- Rendered next to the HTML docs at [https://kdeldycke.github.io/meta-package-manager/man/](https://kdeldycke.github.io/meta-package-manager/man/), with browser-viewable HTML siblings ([live index](cli-parameters.md#man-pages)).

Downstream packagers can regenerate them from source as part of their build phase:

```{code-block} shell-session
$ click-extra wrap --man --output-dir /usr/share/man/man1/ meta_package_manager.cli:mpm
```

The `module:function` notation skips the `mpm` console-script entry point (which dispatches through `__main__:main` and hides the Click command behind a lazy import). The generator honors `SOURCE_DATE_EPOCH` for reproducible builds. See the [`click-extra` man-page reference](https://kdeldycke.github.io/click-extra/man-page.html#generating-man-pages) for other invocation forms (uvx for build sandboxes, `.py` file paths, and the programmatic API).

## Default dependencies

This is a graph of the default, main dependencies of the Python package:

```mermaid assets/dependencies.mmd
:align: center
```

## Extra dependencies

By default, `mpm` supports TOML [configuration files](configuration.md) and all standard [table formats](https://kdeldycke.github.io/click-extra/table.html#table-formats). Optional extras unlock additional configuration file formats, table output formats, and SBOM generation:

````{list-table}
:header-rows: 1
:widths: 10 40 50
* - Extra
  - Install command
  - Unlocks
* - `hjson`
  - ```{code-block} shell-session
    $ uv pip install meta-package-manager[hjson]
    ```
  - - [HJSON](https://kdeldycke.github.io/click-extra/config.html#hjson) config files: `--config mpm.hjson`
    - [`hjson` table format](https://kdeldycke.github.io/click-extra/table.html#table-formats): `--table-format hjson`
* - `json5`
  - ```{code-block} shell-session
    $ uv pip install meta-package-manager[json5]
    ```
  - - [JSON5](https://kdeldycke.github.io/click-extra/config.html#json5) config files: `--config mpm.json5`
* - `jsonc`
  - ```{code-block} shell-session
    $ uv pip install meta-package-manager[jsonc]
    ```
  - - [JSONC](https://kdeldycke.github.io/click-extra/config.html#jsonc) config files: `--config mpm.jsonc`
* - `sbom-offline`
  - ```{code-block} shell-session
    $ uv pip install meta-package-manager[sbom-offline]
    ```
  - - CycloneDX and SPDX SBOM generation from local data: {doc}`mpm sbom <sbom>`
* - `sbom-online`
  - ```{code-block} shell-session
    $ uv pip install meta-package-manager[sbom-online]
    ```
  - - Network enrichment for `mpm --network sbom`: OSV.dev vulnerability lookups
* - `toml`
  - ```{code-block} shell-session
    $ uv pip install meta-package-manager[toml]
    ```
  - - [`toml` table format](https://kdeldycke.github.io/click-extra/table.html#table-formats): `--table-format toml`
* - `xml`
  - ```{code-block} shell-session
    $ uv pip install meta-package-manager[xml]
    ```
  - - [XML](https://kdeldycke.github.io/click-extra/config.html#xml) config files: `--config mpm.xml`
    - [`xml` table format](https://kdeldycke.github.io/click-extra/table.html#table-formats): `--table-format xml`
* - `yaml`
  - ```{code-block} shell-session
    $ uv pip install meta-package-manager[yaml]
    ```
  - - [YAML](https://kdeldycke.github.io/click-extra/config.html#yaml) config files: `--config mpm.yaml`
    - [`yaml` table format](https://kdeldycke.github.io/click-extra/table.html#table-formats): `--table-format yaml`
````

````{tip}
Install all extras at once with:

```{code-block} shell-session
$ uv pip install meta-package-manager[hjson,json5,jsonc,sbom-offline,sbom-online,toml,xml,yaml]
```

Or with `pip`:

```{code-block} shell-session
$ pip install meta-package-manager[hjson,json5,jsonc,sbom-offline,sbom-online,toml,xml,yaml]
```

When working from a cloned repository, [`uv sync`](https://docs.astral.sh/uv/reference/cli/#uv-sync) installs all runtime extras plus dev groups (`test`, `docs`, `typing`) in one shot:

```{code-block} shell-session
$ uv sync --all-extras --all-groups
```
````
