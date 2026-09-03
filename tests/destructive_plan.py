# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
"""The plan driving the destructive install/remove round-trips.

Which package each manager installs and removes, which managers cannot
complete that round-trip on a given host, and which of them may not run at the
same time as another. Kept out of `conftest.py` because the whole of it serves
three test modules: the shared fixtures are what a reader opens conftest for.
"""

from __future__ import annotations

import os
import re
import subprocess
from shutil import which

import pytest
from extra_platforms import is_github_ci, is_linux, is_windows, is_x86_64
from pytest import param

from meta_package_manager.dispatch import SHARED_LOCK_FAMILIES
from meta_package_manager.pool import pool

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable


PACKAGE_IDS = {
    # Purpose-built empty Zsh plugin, shared with zinit below: nothing to source,
    # nothing to break, and it is the ecosystem's established inert package.
    # An application of AM's own catalog. Declares no install operation, since
    # installing blocks on an escalation prompt, so the round-trip auto-skips.
    "am": "appimageupdate",
    "antidote": "zdharma-continuum/null",
    # Declares no install operation: the round-trip auto-skips.
    "antigen": "zdharma-continuum/null",
    "apk": "nyancat",
    "apm": "markdown-pdf",
    "apt": "nyancat",
    "apt-cyg": "tree",
    "apt-mint": "nyancat",
    "aptitude": "nyancat",
    "asdf": "jq",
    # An AUR package rather than a repository one, so the round-trip exercises
    # the half that makes aura an AUR helper. Prebuilt, so no compile step.
    "aura": "yay-bin",
    # A pure-Bash argument parser from basalt's own author, no build step.
    "basalt": "hyperupcall/bash-args",
    # Declares no install operation: the round-trip auto-skips. bin keys every
    # other operation on the installed binary's absolute path, so that is the
    # shape an identifier takes here.
    "bin": "/usr/local/bin/bin",
    # A Neovim version, which is what bob calls a package. Deliberately a
    # released tag and not `nightly`: bob installs the rolling channel happily,
    # but it appears in no catalog listing, and mpm resolves an untied package
    # through the catalog before installing it, so the round-trip would fail on
    # a name the tool itself accepts. A tag is also reproducible where the
    # nightly of the day is not.
    "bob": "v0.11.7",
    # A one-file terminal-colour helper from bpkg's own organisation.
    "bpkg": "bpkg/term",
    "brew": "nyancat",
    "bun": "cowsay",
    "cargo": "fsays",
    "cask": "itsycal",
    "cave": "base/figlet",
    "choco": "hyperfine",
    # A Nim release, choosenim's packages being toolchains. Listed in the
    # catalog, so mpm's pre-install search resolves it. The remove leg cannot
    # run here: see REMOVE_REFUSES_INSTALLED below.
    "choosenim": "2.0.0",
    "chromebrew": "sl",
    # A plugin of the official marketplace, named with the `plugin@marketplace`
    # form every verb takes.
    "claude-code-plugins": "pyright-lsp@claude-plugins-official",
    "composer": "ralouphie/getallheaders",
    "conda": "pytz",  # Pure-Python, zero-dependency leaf on the default channel.
    # One of the registry's few "executables" entries, so a --global install has
    # something to place in the prefix.
    "clib": "stephenmathieson/tabs-to-spaces",
    "cpan": "Try::Tiny",
    "deb-get": "deb-get",
    # devkitPro's repositories carry console toolchains and their libraries, not
    # the usual distro fare: no nyancat. The GBA example sources are the lightest
    # leaf package, and nothing depends on them.
    "dkp-pacman": "gba-examples",
    "dnf": "nyancat",
    "dnf5": "nyancat",
    # Microsoft's canonical sample .NET tool: a 26 KB, zero-dependency ASCII bot
    # that only writes to stdout. It opts into `RollForward=LatestMajor`, so it
    # still runs on a machine carrying no .NET 8 runtime.
    "dotnet": "dotnetsay",
    # A Lean toolchain, which is what elan calls a package. Pinned to a concrete
    # release rather than `stable`: the listing resolves a channel to its
    # concrete name, so removing what `stable` installed would look up an id the
    # inventory never reports. Every toolchain is a large download, so the round
    # trip is expensive wherever elan is actually present.
    "elan": "leanprover/lean4:v4.33.0",
    # A tiny, dependency-free GNU ELPA package: pure elisp with no build step,
    # so the round-trip stays cheap wherever Emacs is present.
    "emacs": "queue",
    "emerge": "games-misc/nyancat",
    "eopkg": "sl",
    "fink": "figlet",
    # Same inert, empty repository the Zsh plugin managers use: Fisher extracts
    # no function, completion or conf.d script from it, so the round-trip
    # exercises the clone and the fish_plugins bookkeeping and nothing else.
    "fisher": "zdharma-continuum/null",
    "flatpak": "org.gnome.Calculator",
    "fwupd": "f95c9218acd12697af946874bfe4239587209232",  # No-op without device.
    # An SDK component. `kubectl` is one of the smallest that is not a
    # dependency of the core install, so removing it again is safe.
    "gcloud": "kubectl",
    "gem": "paint",
    # A Nerd Font, which is what getnf calls a package. One of the smallest
    # archives upstream publishes, and a long-standing Google font, so the
    # round-trip stays cheap and the name survives a Nerd Fonts release.
    "getnf": "ShareTechMono",
    "gext": "caffeine@patapon.info",
    # A tiny script-based extension (a bare git clone), from a GitHub CLI maintainer.
    "gh-ext": "mislav/gh-branch",
    # A tool version, which is what ghcup calls a package. `hls` rather than a
    # GHC: every ghcup artifact is a large download, and the language server is
    # among the lighter ones. Pinned so the round-trip does not depend on
    # whatever the current release happens to be.
    "ghcup": "hls-2.9.0.1",
    # An official example command: tiny, dependency-free and quick to compile.
    "go": "golang.org/x/example/hello",
    "guix": "hello",
    # The same binary the `go` entry above installs, under the name gup keys
    # on. Declares no install operation: the round-trip auto-skips.
    "gup": "hello",
    "haxelib": "hxjsonast",  # Tiny zero-dependency JSON parser.
    # A channel, which is what juliaup calls a package. An old released series
    # rather than `release`: every Julia is a large download, and removing the
    # channel the host actually uses is what `remove` refuses outright.
    # janet-lang's own argument parser: pure Janet, so no compiler is involved.
    # A git URL, which is the only form `hyprpm add` takes; `remove` accepts it
    # too, so the round-trip is symmetric. Needs headers from a prior
    # `hyprpm update`, so it only runs on a real Hyprland host.
    "hyprpm": "https://github.com/hyprwm/hyprland-plugins",
    "jpm": "argparse",
    # The General registry's canonical example package: pure Julia, no
    # dependencies, and it exists precisely to be installed by tests.
    "julia": "Example",
    "juliaup": "1.6",
    "krew": "ctx",  # Tiny context-switcher plugin of krew's own index.
    # Declares no install operation: the round-trip auto-skips. lazy.nvim manages
    # itself, so it is a real entry of its own inventory.
    "lazy": "lazy.nvim",
    # Pure-Lua table pretty-printer, one file and no dependencies.
    "luarocks": "inspect",
    # A shell script in LURE's default recipe repository: no compiler needed,
    # and its build is the fastest in that catalog.
    "lure": "neofetch",
    "macports": "hello",
    "mamba": "zstd",
    "mas": "747648890",
    "mason": "stylua",  # Telegram (test is always skipped).
    # A plugin of micro's own channel. Tiny, pure Lua, and not bundled with
    # the editor, so the round-trip actually installs and removes something.
    "micro": "bounce",
    # A small, dependency-free TeX package of MiKTeX's own catalog.
    "micromamba": "zstd",
    "miktex": "fancyhdr",
    "mise": "jq",
    "nala": "nyancat",
    # Pure-Nim TOML parser, no dependencies and no compiled artifact.
    "nimble": "parsetoml",
    "nix": "hello",
    "npm": "ms",
    # Tiny single-function plugin of Oh My Fish's own package index.
    "oh-my-fish": "bak",
    # The smallest model in ollama's library, at a few hundred megabytes;
    # every model is a large download and this is the lightest.
    "ollama": "tinyllama:latest",
    "opam": "zarith",  # Small pure-OCaml-adjacent leaf library.
    "opkg": "lolcat",
    "pacaur": "nyancat",
    "pacman": "nyancat",
    "pacstall": "hello",
    "pamac": "nyancat",
    "paru": "nyancat",
    # A small library of pi's own npm scope. The id carries its scheme, which
    # is the form every verb takes.
    # A vim statusline plugin of Pearl's own repository: a git clone with no
    # build. The id carries its repository prefix, which every verb takes.
    "pear": "Text_Password",
    "pearl": "pearl/airline",
    "pi": "npm:@earendil-works/pi-telemetry",
    "pikaur": "nyancat",
    "pip": "pytz",
    "pipx": "pycowsay",
    "pipxu": "pycowsay",
    # conda-forge ships no nyancat, so pixi reuses the binary-store pick. It is a
    # single self-contained Rust binary, built for every platform pixi runs on.
    "pixi": "hyperfine",
    "pkcon": "hello",
    "pkg": "nyancat",
    # pkgit has no catalog of its own: the shipped default config declares
    # exactly one repository, pkgit's own.
    "pkgit": "pkgit",
    "pkg-tools": "nyancat",
    "pkgin": "nyancat",
    # A pantry path rather than the `jq` executable name: both install, but only
    # the path is what `pkgm list` reports back, so only it round-trips.
    "pkgm": "stedolan.github.io/jq",
    # Declares no install operation: the round-trip auto-skips. Every mutating
    # verb needs the package kind as a flag, which an id alone does not carry.
    "platformio-core": "ArduinoJson",
    "pnpm": "ms",
    "ports": "net/nyancat",
    "pwsh-gallery": "Posh-Git",
    # A PyPy rather than a CPython: pyenv builds CPython from source, dragging
    # OpenSSL and readline along with it, where this definition downloads a
    # prebuilt archive. Still a large download, which is the lightest pyenv has.
    "pyenv": "pypy3.11-7.3.20",
    # A toolchain, which is what rustup calls a package, named by release so it
    # resolves to whatever target triple the host runs. Pinned to an old release
    # nobody builds against today, since removing `stable` or `nightly` would
    # take the host's working Rust with it. Every rustup artifact is a large
    # download, so this is the lightest available rather than a small one, as
    # with `sdkman` below.
    # A one-module pure-Racket package with no build step.
    "raco": "uuid",
    # A Lisp implementation: roswell lists and installs those, never Quicklisp
    # systems (see the Roswell class docstring).
    "roswell": "sbcl-bin",
    "rustup": "1.60.0",
    "scoop": "main/hyperfine",
    "sdkman": "jbang",
    "sfsu": "main/hyperfine",
    # Declares no install operation: the round-trip auto-skips.
    "sheldon": "zsh-autosuggestions",
    # Declares no install operation: the round-trip auto-skips. `add` takes a
    # source repository rather than one skill, so there is nothing per-package
    # to install; the name below is what `remove` accepts.
    "skills": "deploy-to-vercel",
    "slapt-get": "nano",
    "snap": "hello-world",
    "soar": "bat",  # Single-file static binary from the soarpkgs registry.
    "sorcery": "figlet",
    # Spack builds everything from source, so the round-trip needs the cheapest
    # thing in the catalog: zlib compiles in a few seconds and pulls in nothing
    # beyond the compiler wrapper and make.
    "spack": "zlib",
    "steamcmd": "1007",  # Steamworks SDK Redist.
    "stew": "sharkdp/hyperfine",
    # SVR4 packages install from local datastreams, not a repository: install is
    # unimplemented so the destructive round-trip auto-skips.
    "sun-tools": "SUNWzlib",
    "swupd": "curl",  # A small additive bundle: os-core never depends on it.
    "tazpkg": "nano",  # Used by tazpkg's own test suite.
    "tlmgr": "lipsum",  # Pure dummy-text package: a leaf with no style dependencies.
    "topgrade": "topgrade",  # Declares no install operation: the round-trip auto-skips.
    "trizen": "nyancat",
    "urpmi": "figlet",
    "uv": "pytz",
    "uvx": "pycowsay",
    # A single-file Vim plugin with no dependencies. vim.pack keys packages on
    # their source URL, the only id it accepts for an install.
    # A tiny header-only library, and one of the smallest ports vcpkg
    # carries. The triplet is left off so it resolves to the host default.
    "vcpkg": "zlib",
    "vim-pack": "https://github.com/tpope/vim-sensible",
    # Zero-dependency and ships a bin: Volta manages CLI tools, so the usual
    # bin-less npm pick (ms) is out.
    "volta": "nanoid",
    "vscode": "tamasfe.even-better-toml",
    "vscodium": "tamasfe.even-better-toml",
    "winget": "sharkdp.hyperfine",
    "xbps": "sl",
    "yazi": "yazi-rs/plugins:full-border",
    # Declares no install operation, since downloading an Xcode always
    # authenticates interactively: the round-trip auto-skips. A marketing
    # version is what xcodes addresses a bundle by.
    "xcodes": "16.2",
    # A box. Chosen for being tiny by Vagrant standards and published by
    # HashiCorp itself, so it stays available; every box is still a large
    # download, which is the lightest this ecosystem offers.
    "vagrant": "hashicorp/bionic64",
    "yarn": "ms",
    "yarn-berry": "ms",
    "yay": "nyancat",
    "yum": "nyancat",
    "zerobrew": "nyancat",
    # Declares no install operation, `0install add` needing a pet name and a
    # feed URI where mpm carries one id: the round-trip auto-skips. A pet name
    # is what removal takes, and the user invents it, so there is no canonical
    # one to name here.
    "zeroinstall": "zeroinstall",
    # Zinit's own do-nothing plugin: an empty repository it documents for
    # ice-only usage, so loading and deleting it runs no third-party code.
    # Declares no install operation: the round-trip auto-skips.
    # A leaf Raku distribution: pure Raku, no dependencies of its own.
    "zef": "hyperize",
    "zim": "zsh-users/zsh-completions",
    "zinit": "zdharma-continuum/null",
    # Declares no install operation: the round-trip auto-skips.
    "zplug": "zdharma-continuum/null",
    # A Zig version, which is what zvm calls a package. A released tag rather
    # than `master`: every Zig is a large download, and a tag is reproducible
    # where the rolling channel of the day is not.
    "zvm": "0.13.0",
    "zypper": "nyancat",
}
"""Package IDs used by the destructive install/remove tests, one per manager.

Each entry is fed to `mpm --<manager_id> install <package_id>` immediately followed
by `mpm --<manager_id> remove <package_id>`, so the package is both added to and
removed from the host running the test. Each ID is picked to keep that round-trip cheap
and free of side effects:

- Tiny and quick to install, with no dependency tree, no services or daemons, and no
  `/etc` configuration: just a self-contained binary.
- Not a tool the OS, the manager itself, or common scripts are likely to depend on.
  Ubiquitous utilities (`wget`, `curl`, `git`, `jq`, ...) are avoided: they are
  usually already installed (so the install step is a no-op) and removing them can break
  the host.
- Preferably from the Rust or Go ecosystems, which rarely pull in extra dependencies.

Wherever a manager exposes general-purpose binaries the same low-impact tools are reused
for consistency: `nyancat` (a single-file C binary packaged by nearly every Linux
distro, Homebrew, FreeBSD as `net/nyancat`, OpenBSD and pkgsrc as `misc/nyancat`),
GNU `hello` for the functional managers (Guix, Nix) and `hyperfine` for the Windows
binary stores and `stew`. Distros that lack `nyancat` fall back to `sl`
(Chromebrew, Solus, Void), `figlet` (another tiny dependency-free C binary, for
Exherbo, Fink, Mageia and Source Mage), `lolcat` (OpenWrt) or `nano` (Slackware's
official tree carries none of the above, so `slapt-get` mirrors `tazpkg`).
Language and application managers use the smallest inert package native to their
ecosystem (`ms` for npm and Yarn, `pycowsay` for the pipx-style installers that
require a console-script entry point, ...).

```{warning}

`fwupd` flashes real firmware. Its ID is a release with no matching device on CI
runners, where the install is therefore a no-op. Never run the destructive `fwupd`
test on hardware that the ID actually targets.
```

```{note}

A few managers cannot offer a small binary: `sdkman` only ships full SDKs
(`jbang` is its lightest candidate), and `mas` needs a signed App Store app (its
test is skipped anyway). `deb-get` has no real per-package install, so it
references itself, and `topgrade` declares no install operation at all, so its
round-trip auto-skips. `gh-ext` references its extension by the `owner/repo`
slug: the only id `gh extension install` accepts, and the id scheme its
`installed` operation reports.
```

Only to be used for destructive tests.
"""

# Every manager mpm ships gets an entry: the built-in classes and the bundled
# config-defined managers alike. The hermetic test_manager_definition suite locks the
# latter's command mapping, but only the destructive round-trip proves the mapped
# commands work against the real tool on hosts that carry it.
assert set(PACKAGE_IDS) == set(pool.known_manager_ids)


DESTRUCTIVE_TEST_FAMILIES: dict[str, frozenset[str]] = {
    # `pip` and `uv` both round-trip the same package ({data}`PACKAGE_IDS` maps
    # both to `pytz`) in the active virtual environment, so two workers would
    # race on one `site-packages`.
    "active venv": frozenset({"pip", "uv"}),
    # `pipx` and `uvx` both install `pycowsay`, whose console-script shim lands
    # in the same default bin directory (`~/.local/bin`) wherever the
    # environment does not split them with `UV_TOOL_BIN_DIR`.
    "tool shims": frozenset({"pipx", "uvx"}),
}
"""Managers whose *destructive tests* collide on a shared install target.

The test-suite complement of
{data}`~meta_package_manager.dispatch.SHARED_LOCK_FAMILIES`: those families
record managers contending for one backend lock at runtime, while the entries
here only collide because of what the destructive round-trips themselves
install, so they belong to the suite rather than to `mpm`. Family names carry
a space on purpose, keeping them clear of the manager-id namespace the other
group names live in.
"""

# A manager cannot need both catalogs: a backend-lock family already
# serializes its members, making a test-level entry for them redundant.
assert not any(
    members & family.members
    for members in DESTRUCTIVE_TEST_FAMILIES.values()
    for family in SHARED_LOCK_FAMILIES
)

_DESTRUCTIVE_GROUPS: dict[str, str] = {
    manager_id: name
    for name, members in (
        *((family.backend, family.members) for family in SHARED_LOCK_FAMILIES),
        *DESTRUCTIVE_TEST_FAMILIES.items(),
    )
    for manager_id in members
}
"""Scheduling group of every manager whose destructive tests may not run alone."""


def destructive_group(manager_id: str) -> str:
    """Resolve the `xdist_group` a destructive test driving `manager_id` runs in.

    Managers sharing a backend lock
    ({data}`~meta_package_manager.dispatch.SHARED_LOCK_FAMILIES`) or an install
    target ({data}`DESTRUCTIVE_TEST_FAMILIES`) collapse into one group, which
    `--dist=loadgroup` schedules serially on a single worker, mirroring `mpm`'s
    own grouped fan-out; every other manager gets a group of its own and runs
    in parallel with the rest.
    """
    return _DESTRUCTIVE_GROUPS.get(manager_id, manager_id)


SHORT_FAILURE_TIMEOUT = 10
"""Seconds to cap a destructive install that is *expected* to fail.

The managers in {data}`INSTALL_REMOVE_BLOCKED_WHEN` cannot complete a real install in the
test environment. Most fail within a second (a permission error, a missing remote, an
empty search), but a few (`scoop` and `sfsu` on Windows, `pwsh-gallery` on macOS)
hang with no error until the state-change timeout would otherwise elapse. Capping their
CLI calls keeps the doomed attempts cheap: long enough for the fast failures to surface,
short enough that the genuine hangs do not dominate the destructive job's wall-clock.
"""


def gh_unauthenticated() -> bool:
    """Whether the `gh` CLI is present but holds no usable credentials.

    `gh` refuses to run `extension install` unauthenticated, so the gh-ext
    destructive round-trip can only succeed where it resolves a token. ``gh auth
    token` probes the resolved credentials (stored logins and `GH_TOKEN``-style
    environment variables alike) without any network call. A missing `gh` is not
    flagged: selection then finds no available manager and the test already exits on
    its "No manager selected" path.
    """
    gh_path = which("gh")
    if not gh_path:
        return False
    probe = subprocess.run((gh_path, "auth", "token"), capture_output=True, check=False)
    return probe.returncode != 0


def cpan_install_blocked() -> bool:
    """Whether `cpan install` cannot complete on this host.

    Derived from measured CI results rather than from the permissions of Perl's
    site library, which do not predict the outcome: that tree is root-owned on
    macOS too, yet the round-trip succeeds there. The install fails only on the
    x86 Linux runners; the arm64 image of the same Ubuntu release ships a Perl
    the unelevated user can install into, and macOS resolves a writable target
    of its own.

    Keep this keyed on evidence. A flat `is_linux` was wrong on arm64, and a
    writability probe would have been wrong on macOS in the other direction.
    `is_x86_64` rather than a negated ARM test, so the pair of images actually
    measured is what the predicate names: a third Linux architecture would be an
    unknown, not an assumed failure.
    """
    return is_linux() and is_x86_64()


def pear_install_blocked() -> bool:
    """Whether `pear install` cannot complete on this host.

    PEAR gates an install on exactly one test of its own, refusing with `Cannot
    install, php_dir for channel "pear.php.net" is not writeable by the current
    user`, so the same directory is probed here rather than the platform
    guessed from. A distribution's PHP roots that directory at `/usr/share/php`
    and owns it as root, blocking an unelevated round-trip; a PEAR relocated to
    a user-owned prefix is not blocked, and the probe follows it either way.

    mpm leaves PEAR's privileged markers dormant, being a dual-scope language
    manager, so nothing escalates the install on the manager's behalf.
    """
    pear_path = which("pear")
    if not pear_path:
        return False
    probe = subprocess.run(
        (pear_path, "config-get", "php_dir"),
        capture_output=True,
        check=False,
        text=True,
        encoding="UTF-8",
    )
    php_dir = probe.stdout.strip()
    if probe.returncode != 0 or not php_dir:
        return False
    return not os.access(php_dir, os.W_OK)


def snap_sudo_unavailable() -> bool:
    """Whether snap's privileged install cannot run unattended on this host.

    mpm sudo-escalates snap (snapd refuses unprivileged state changes), so the
    round-trip completes only where `sudo` needs no password. The platform
    cannot answer that: GitHub's runners grant passwordless sudo, a typical
    workstation password-gates it, and a provisioned box may do either, so the
    state is probed live rather than inferred from `is_github_ci`.

    `sudo --non-interactive true` asks the question the install actually asks,
    which is whether a command can escalate without a prompt. `--validate` asks
    a different one, refreshing the credential cache, and answers non-zero on a
    host whose `NOPASSWD` rule sits beside a password-requiring group rule even
    though every command still runs unprompted.
    """
    sudo_path = which("sudo")
    if not sudo_path:
        return True
    probe = subprocess.run(
        (sudo_path, "--non-interactive", "true"),
        capture_output=True,
        check=False,
    )
    return probe.returncode != 0


def gcloud_components_blocked() -> bool:
    """Whether gcloud's component manager cannot mutate this installation.

    Two independent layouts break `components install` on the runner fleet,
    and both vary across its images and architectures, so the state is probed
    live rather than assumed from the platform. A package-manager install
    disables the component manager outright (*"You cannot perform this action
    because the Google Cloud CLI component manager is disabled for this
    installation."*), which the exit code of a read-only `components list`
    already exposes. A tarball layout whose SDK root is owned by root passes
    that first probe yet still refuses the unelevated mutation, so the
    resolved `installation.sdk_root` is then checked for write access: the
    arm64 Ubuntu image ships a writable root where the x86 one does not. A
    missing `gcloud` is not flagged, as selection then finds no available
    manager and the test already exits on its "No manager selected" path.
    """
    gcloud_path = which("gcloud")
    if not gcloud_path:
        return False
    probe = subprocess.run(
        (gcloud_path, "components", "list", "--quiet"),
        capture_output=True,
        check=False,
    )
    if probe.returncode != 0:
        return True
    root_probe = subprocess.run(
        (gcloud_path, "info", "--format=value(installation.sdk_root)"),
        capture_output=True,
        check=False,
        text=True,
        encoding="UTF-8",
    )
    sdk_root = root_probe.stdout.strip()
    return bool(sdk_root) and not os.access(sdk_root, os.W_OK)


def claude_marketplace_missing() -> bool:
    """Whether Claude Code has no marketplace to resolve a plugin from.

    A plugin id names its marketplace, and `claude plugin install` resolves it
    against the ones configured for the current user. A fresh host has none, so
    the install fails for want of a registry rather than for any defect, which
    is a condition of the machine rather than of the platform: the maintainer's
    own workstation carries two, and a runner carries none.
    """
    marketplaces = which("claude")
    if not marketplaces:
        # A missing CLI is not flagged: selection then finds no available
        # manager and the test exits on its "No manager selected" path.
        return False
    result = subprocess.run(
        ("claude", "plugin", "marketplace", "list"),
        capture_output=True,
        text=True,
        encoding="UTF-8",
    )
    return "No marketplaces configured" in result.stdout


def pearl_bash_too_old() -> bool:
    """Whether the host's Bash predates what Pearl's hook functions need.

    Pearl requires Bash `4.1` and warns on every invocation when it does not
    have it. Below that its read-only listings still work while an install
    fails inside the package's own hooks, so the round-trip breaks for a
    property of the machine rather than of `mpm`. macOS ships `3.2`, which is
    what this catches; any newer Bash earlier on `PATH` satisfies it.
    """
    bash = which("bash")
    if not bash:
        return False
    result = subprocess.run(
        (bash, "--version"),
        capture_output=True,
        text=True,
        encoding="UTF-8",
    )
    match = re.search(r"version\s+(\d+)\.(\d+)", result.stdout)
    if not match:
        return False
    return (int(match.group(1)), int(match.group(2))) < (4, 1)


def rpm_distro_missing() -> bool:
    """Whether this host is not backed by a working RPM distribution.

    The RPM front-ends (`dnf`, `dnf5`, `yum`, `zypper`) resolve nothing on a host
    whose RPM database was never populated: they find no release version and no
    repositories, and fail at the search step before reaching the privileged
    install. A Debian-based runner carrying one of their binaries is exactly that
    host.

    Keyed on the database rather than on the platform, so a real openSUSE or
    Fedora machine runs the round-trip instead of inheriting a CI artifact. The
    flat `is_linux` this replaces blocked every Linux, which meant the four
    front-ends were never exercised anywhere.
    """
    rpm_path = which("rpm")
    if not rpm_path:
        return True
    probe = subprocess.run(
        # One dot per installed package, so the output stays small on a full host.
        (rpm_path, "--query", "--all", "--queryformat", "."),
        capture_output=True,
        check=False,
        text=True,
        encoding="UTF-8",
    )
    return probe.returncode != 0 or not probe.stdout.strip()


def flatpak_install_blocked() -> bool:
    """Whether a flatpak install cannot complete unattended on this host.

    Two gates, and an install needs both. It needs a configured remote to resolve
    the application from, which a bare flatpak has none of. It then needs polkit
    to authorize the system-scope deploy, which an unattended session cannot
    answer for: `pkcheck` reports `auth_admin` there, and flatpak resolves the
    whole application before dying on `Flatpak system operation Deploy not
    allowed for user`, a late failure that reads like an mpm fault and is not one.

    Probed live rather than inferred: a desktop install configures Flathub and
    clears the polkit prompt from its session, while a CI image and a headless SSH
    login clear neither. Root needs no polkit at all and is let through.

    Every uncertainty answers "blocked", since the cost of skipping a round-trip
    that would have worked is one lost signal, against a red run for a property of
    the host.
    """
    flatpak_path = which("flatpak")
    if not flatpak_path:
        return True
    remotes = subprocess.run(
        (flatpak_path, "remotes", "--columns=name"),
        capture_output=True,
        check=False,
        text=True,
        encoding="UTF-8",
    )
    if remotes.returncode != 0 or not remotes.stdout.strip():
        return True
    if getattr(os, "geteuid", lambda: 1)() == 0:
        return False
    pkcheck_path = which("pkcheck")
    if not pkcheck_path:
        return True
    authorized = subprocess.run(
        (
            pkcheck_path,
            "--action-id",
            "org.freedesktop.Flatpak.app-install",
            "--process",
            str(os.getpid()),
        ),
        capture_output=True,
        check=False,
    )
    return authorized.returncode != 0


INSTALL_REMOVE_BLOCKED_WHEN: dict[str, bool | Callable[[], bool]] = {
    # Claude Code resolves a plugin through the marketplaces configured for the
    # user, and a fresh host has none, so the install fails for want of a registry.
    "claude-code-plugins": claude_marketplace_missing,
    # choco installs to an admin-only location the unelevated CI process cannot write to.
    "choco": is_github_ci,
    # cpan writes to the system Perl tree, out of reach only on the x86 Linux runners.
    "cpan": cpan_install_blocked,
    # pear writes to the PHP interpreter's php_dir, root-owned on a distro install.
    "pear": pear_install_blocked,
    # The RPM front-ends resolve no package where the RPM database is empty, which the
    # Debian-based runners are, so they fail before the privileged install step.
    "dnf": rpm_distro_missing,
    "dnf5": rpm_distro_missing,
    "yum": rpm_distro_missing,
    "zypper": rpm_distro_missing,
    # flatpak needs a remote to resolve apps from and polkit to authorize the
    # system-scope deploy; an unattended session clears neither.
    "flatpak": flatpak_install_blocked,
    # basalt refuses every command, the read-only listing included, without a GitHub
    # token file of its own, and needs the environment its shell-init snippet exports.
    # Neither is set up on a runner.
    "basalt": is_github_ci,
    # fwupd flashes firmware; the CI VMs expose no flashable hardware, so the install
    # exits non-zero.
    "fwupd": True,
    # gem carries no blocker: RubyGems falls back to a user install when the system
    # gem directory is not writable, so the round-trip completes on every runner,
    # Linux included. The `is_linux` blocker that used to sit here asserted a failure
    # that no longer happens on any image.
    # gcloud refuses component mutations when it was installed through a package
    # manager, but runner images ship both that layout and the tarball one whose
    # component manager works, so the state is probed live per host.
    "gcloud": gcloud_components_blocked,
    # gh refuses extension installs without credentials; tests.yaml feeds the workflow
    # token to the destructive CI step so this round-trip runs for real there.
    "gh-ext": gh_unauthenticated,
    # mas resolves an install through an App Store search that finds nothing for the
    # numeric id on the headless runners, so the install fails.
    "mas": is_github_ci,
    # Pearl's hook functions need Bash 4.1; macOS ships 3.2, where an install
    # fails inside the package's own hooks while the listings still work.
    "pearl": pearl_bash_too_old,
    # pixi resolves its cache directory from the Windows user profile, which the
    # suite's isolated HOME leaves unset: the install aborts on "could not determine
    # default cache directory" before reaching the package. Same shape as the pnpm
    # entry below, an environment the runner never sets up rather than a manager bug.
    "pixi": is_windows,
    # pkcon hands mutations to packagekitd, which authorizes them through polkit; the
    # headless runner ships no policy permitting unattended installs for the unelevated
    # user, so the transaction is refused. See the Pkcon class docstring for why mpm
    # does not sudo-escalate pkcon itself.
    "pkcon": is_github_ci,
    # pnpm add --global needs a PNPM_HOME (from `pnpm setup`) the runners do not set up.
    "pnpm": is_github_ci,
    # pwsh-gallery's PSResourceGet lookup is unreliable on the runners: Find-PSResource
    # hangs on the macOS image and returns a case-mismatched name on Linux, so the install
    # never resolves the package.
    "pwsh-gallery": is_github_ci,
    # scoop install hangs until the timeout on the GitHub Windows runners; sfsu wraps it.
    "scoop": is_github_ci,
    "sfsu": is_github_ci,
    # mpm sudo-escalates snap (snapd rejects unprivileged state changes), so the
    # blocker turns on whether that sudo runs unattended, which is a property of
    # the host rather than of CI: a passwordless workstation completes the
    # round-trip exactly as a runner does.
    "snap": snap_sudo_unavailable,
    # steamcmd can only install titles owned by an authenticated account; the runners'
    # anonymous session is not logged in, so the install fails. No environment satisfies it.
    "steamcmd": True,
}
"""Managers that cannot complete a real install, mapped to the condition under which
that is true. Read an entry as "`<manager>` is blocked when `<condition>`".

The name carries the polarity so the values do not have to: a bare `is_github_ci` next
to a manager id reads as a *statement about* that manager unless the mapping says which
way round it goes. The inverse shape (listing where each manager *is* installable) was
weighed and dropped: fifteen of these seventeen entries are naturally phrased as "blocked
when X", so inverting would spell them all as negation lambdas to spare the two constants.

Rather than skip these managers (which would also drop their dispatch coverage and any
signal that they still fail the *expected* way), the destructive install/remove test drives
each one's `install` anyway, caps the doomed CLI call with
{data}`SHORT_FAILURE_TIMEOUT`, and asserts that mpm reports the stable failure: exit code
`1` and a ``Could not install: {package}`` critical message. The follow-up `remove` is
skipped, since the failed install left nothing to remove and the working managers already
cover the removal path.

A condition is either a plain `True` for the managers no environment can install, or a
zero-argument callable evaluated per host: `is_github_ci` for GitHub Actions only (a
configured local box can still install), or a live probe like `gh_unauthenticated` or
`rpm_distro_missing` when installability hinges on host state rather than platform. Prefer
a probe: a platform test blocks every machine of that platform, including the ones where
the round-trip would have worked. Resolve one through {func}`install_remove_blocked` rather than calling it
directly, which is what keeps the constants from needing a `lambda` wrapper.

```{note}

The assertion deliberately targets mpm's own `Could not install:` message rather than
the underlying tool's error. The raw tool output is not a stable contract: it is
platform-specific (`pwsh-gallery` times out on macOS but hits a name-case mismatch on
Linux), stage-specific (`dnf`/`zypper`/`flatpak` fail at the search step, never
reaching their privileged install errors), and drifts across tool versions, OS images,
and locales. mpm's failure message is identical everywhere, so the test stays robust.
```
"""


def install_remove_blocked(manager_id: str) -> bool:
    """Whether `manager_id` cannot complete a real install here.

    Resolves the {data}`INSTALL_REMOVE_BLOCKED_WHEN` condition, which is either a
    constant or a callable evaluated against the running host. A manager with no
    entry is not blocked.
    """
    condition = INSTALL_REMOVE_BLOCKED_WHEN.get(manager_id, False)
    return condition() if callable(condition) else condition


REMOVE_REFUSES_INSTALLED: frozenset[str] = frozenset(
    {
        # choosenim selects whatever it installs, and refuses to remove the selected
        # toolchain: `Error: Cannot remove current version.` So the package the
        # install leg just placed is exactly the one the remove leg cannot take back.
        # Removing an *older* toolchain works, which is the path users reach for.
        "choosenim",
    }
)
"""Managers whose `remove` cannot take back what the install leg just installed.

Distinct from {data}`INSTALL_REMOVE_BLOCKED_WHEN`, which covers a failing *install*
and skips the removal for want of anything to remove. Here the install succeeds and
the removal is refused on purpose, so the round-trip is driven in full and the
refusal asserted, keeping the signal that the manager still fails the expected way.

Unconditional rather than host-resolved: the refusal is the tool's own rule, so no
environment satisfies it.
"""


# Unmaintained managers are excluded: their upstreams are unreliable or gone, so a real
# install/remove would only contribute flakiness (see PackageManager.unmaintained).
maintained_manager_ids_and_dummy_package = pytest.mark.parametrize(
    "manager_id,package_id",
    tuple(param(mid, PACKAGE_IDS[mid], id=mid) for mid in pool.maintained_manager_ids),
)
