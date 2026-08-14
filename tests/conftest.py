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
"""Fixtures, configuration and helpers for tests."""

from __future__ import annotations

import subprocess
import sys
from functools import partial
from operator import attrgetter
from pathlib import Path
from shutil import which

import pytest

# Shared version-gated TOML reader, re-exported for the whole test suite.
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]  # noqa: F401

# Pre-load invocation helpers to be used as pytest's fixture.
from click_extra.pytest import create_config, runner  # noqa: F401
from extra_platforms import is_github_ci, is_linux, is_windows, is_x86_64
from extra_platforms.pytest import skip_hermetic_build
from pytest import fixture, param

from meta_package_manager.cli import mpm
from meta_package_manager.pool import ManagerPool, manager_classes, pool

from .fake_manager import FakeManager, TimingOutFakeManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable

    from _pytest.config import Config

PROJECT_ROOT = Path(__file__).parent.parent
"""Repository root, holding the committed artifacts the `test_docs` guards
check and the `.git` directory whose presence marks a developer checkout."""


def pytest_addoption(parser):
    """Add custom command line options.

    Based on [Pytest's documentation examples](https://docs.pytest.org/en/latest/example/simple.html#control-skipping-of-tests-according-to-command-line-option).

    By default, runs non-destructive tests and skips destructive ones.
    """
    parser.addoption(
        "--run-destructive",
        action="store_true",
        default=False,
        help="Run the subset of tests that are marked as destructive.",
    )
    parser.addoption(
        "--skip-destructive",
        action="store_true",
        default=False,
        help="Skip the subset of tests that are marked as destructive. "
        "Takes precedence over --run-destructive.",
    )

    parser.addoption(
        "--run-non-destructive",
        action="store_true",
        default=True,
        help="Run the subset of tests that are marked as non-destructive.",
    )
    parser.addoption(
        "--skip-non-destructive",
        action="store_true",
        default=False,
        help="Skip the subset of tests that are marked as non-destructive. "
        "Takes precedence over --run-non-destructive.",
    )


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "destructive: mark test as being destructive, "
        "i.e. modifying the system they run on.",
    )
    config.addinivalue_line(
        "markers",
        "integration: mark test as driving a real package manager or the mpm "
        "CLI end-to-end. It cannot run in a hermetic build sandbox; writable-"
        '$HOME builders select the hermetic layer with -m "not integration".',
    )
    config.addinivalue_line(
        "markers",
        "repo_maintenance: mark test as a sync guard comparing a committed "
        "artifact against a regeneration from the installed tooling. Only "
        "meaningful in a git checkout of the repository, not a packager build.",
    )


def solve_destructive_options(config: Config) -> tuple[bool, bool]:
    """Solve the destructive options to determine which tests to run."""
    run_destructive = config.getoption("--run-destructive")
    run_non_destructive = config.getoption("--run-non-destructive")

    # Skip options take precedence over run options.
    if config.getoption("--skip-destructive"):
        run_destructive = False
    if config.getoption("--skip-non-destructive"):
        run_non_destructive = False

    if not run_destructive and not run_non_destructive:
        msg = (
            "Both destructive and non-destructive tests were skipped. No tests to run."
        )
        raise ValueError(msg)

    return run_destructive, run_non_destructive


def pytest_collection_modifyitems(config, items):
    """Apply collection-time markers and skips.

    On top of the command-line destructive-test selection, this classifies the
    integration layer and quarantines the repo-maintenance guards, so a
    downstream packager can run the suite with a single selection and no
    per-module ignore list. See
    https://mpm.run/packaging.html
    """
    run_destructive, run_non_destructive = solve_destructive_options(config)

    # Skip destructive tests.
    if not run_destructive:
        skip_destructive = pytest.mark.skip(reason="skip destructive tests")
        for item in items:
            if "destructive" in item.keywords:
                item.add_marker(skip_destructive)

    # Skip non-destructive tests.
    if not run_non_destructive:
        skip_non_destructive = pytest.mark.skip(reason="skip non-destructive tests")
        for item in items:
            if "destructive" not in item.keywords:
                item.add_marker(skip_non_destructive)

    # Repo-maintenance guards regenerate a committed artifact from the installed
    # tooling and compare: only meaningful while developing mpm, where the
    # tooling versions are pinned. A `.git` directory marks that checkout; a
    # packager building from a tarball or sdist has none.
    in_git_checkout = (PROJECT_ROOT / ".git").exists()

    for item in items:
        # Tag the integration layer: tests driving a real package manager
        # (`test_manager_*`) or the `mpm` CLI end-to-end (`test_cli*`). The
        # bar-plugin suite carries the marker in its own module. A machine-
        # readable marker lets writable-$HOME builders (Alpine, Debian, RPM mock)
        # select `-m "not integration"` instead of hand-listing modules, and
        # frees the classification from the module-naming convention.
        if item.path.name.startswith(("test_manager_", "test_cli")):
            item.add_marker(pytest.mark.integration)

        # The integration layer has no package managers to drive in a hermetic
        # build sandbox. Auto-skip it inside one (detected by `extra_platforms`
        # through `HOME=/homeless-shelter`, as Guix and Nixpkgs both set) so
        # those distributors run a plain `pytest` with no ignores.
        if item.get_closest_marker("integration"):
            item.add_marker(skip_hermetic_build)

        # Drop the repo-maintenance guards outside a developer checkout.
        if item.get_closest_marker("repo_maintenance") and not in_git_checkout:
            item.add_marker(
                pytest.mark.skip(reason="repo-maintenance guard: not a git checkout"),
            )


def pytest_report_header(config: Config, start_path: Path) -> tuple[str, ...]:
    """Display destructive options status in test report header."""
    run_destructive = config.getoption("--run-destructive")
    skip_destructive = config.getoption("--skip-destructive")
    run_non_destructive = config.getoption("--run-non-destructive")
    skip_non_destructive = config.getoption("--skip-non-destructive")
    run_destructive_tests, run_non_destructive_tests = solve_destructive_options(config)
    return (
        f"--run-destructive={run_destructive}",
        f"--skip-destructive={skip_destructive}",
        f"--run-non-destructive={run_non_destructive}",
        f"--skip-non-destructive={skip_non_destructive}",
        f"Run destructive tests: {run_destructive_tests}",
        f"Run non-destructive tests: {run_non_destructive_tests}",
    )


@fixture(autouse=True)
def isolate_user_config(isolated_app_dir):
    """Hide the developer's real `mpm` configuration from the test suite.

    Any `config.toml` in the host configuration folder bleeds into every
    in-process CLI invocation: a local `cpan = false`, for instance, silently
    drops the manager from the default selection, so `check_manager_selection`
    assertions that expect the full default set fail locally while passing in
    CI, which has no such file.

    Autouse alias of click-extra's
    {func}`~click_extra.pytest.isolated_app_dir` fixture, which repoints
    {func}`click.get_app_dir`-based config discovery at a fresh empty
    directory. `HOME` is left intact so the integration layer keeps
    detecting the real package managers, and the override does not propagate
    to subprocesses. Tests that exercise config loading pass ``--config
    <path>`` explicitly, which bypasses the default search pattern and is
    therefore left untouched.
    """
    return isolated_app_dir


@fixture
def invoke(runner):  # noqa: F811
    yield partial(runner.invoke, mpm)


@fixture
def stub_run_cli(monkeypatch):
    """Replace a manager's `run_cli` with a canned-output stub.

    Returns a `stub(manager, output)` callable: every `run_cli` call on
    `manager` then returns `output` without spawning a subprocess. The
    workhorse of the output-parsing tests (`test_manager_*`). To assert on
    the arguments a manager builds instead, see {func}`capture_run_cli`.
    """

    def stub(manager, output: str) -> None:
        monkeypatch.setattr(manager, "run_cli", lambda *args, **kwargs: output)

    return stub


@fixture
def capture_run_cli(monkeypatch):
    """Replace a manager's `run_cli` with a positional-argument recorder.

    Returns a `capture(manager, output="")` callable, which patches the
    manager and hands back the list every call's positional arguments are
    appended to, so a test can assert on the exact CLI the manager builds.
    """

    def capture(manager, output: str = "") -> list[tuple]:
        calls: list[tuple] = []

        def fake_run_cli(*args, **kwargs):
            calls.append(args)
            return output

        monkeypatch.setattr(manager, "run_cli", fake_run_cli)
        return calls

    return capture


def _patch_pool_with(monkeypatch, fake):
    """Replace `pool.select_managers` with a generator yielding `fake`.

    Mirrors the runtime knobs (timeout, stop_on_error, dry_run,
    ignore_auto_updates) that
    {meth}`meta_package_manager.pool.ManagerPool._select_managers` would
    forward, so the CLI exercises the same code path it does against real
    managers.
    """

    def fake_select_managers(*args, **kwargs):
        for option in ManagerPool.ALLOWED_EXTRA_OPTION:
            if option in kwargs:
                setattr(fake, option, kwargs[option])
        # Mirror the per-operation stamping done by the real _select_managers so
        # CLI tests resolve timeouts the same way production does.
        op = kwargs.get("implements_operation")
        fake._active_operation = op.name if op else None
        yield fake

    monkeypatch.setattr(pool, "select_managers", fake_select_managers)
    # Expose the fake in the registry too: code paths re-resolving a manager
    # from its ID (like the bar-plugin renderer's upgrade-CLI augmentation)
    # go through `pool.get()` instead of the selection generator.
    monkeypatch.setitem(pool.register, fake.id, fake)
    return fake


@fixture
def fake_pool(monkeypatch):
    """Yield a single deterministic {class}`FakeManager` from the pool.

    Use for CLI plumbing tests (stats lines, table rendering, exit codes)
    that need a stable package set regardless of host PATH.
    """
    return _patch_pool_with(monkeypatch, FakeManager())


@fixture
def slow_fake_pool(monkeypatch):
    """Yield a {class}`TimingOutFakeManager` whose `outdated` exceeds `--timeout`.

    Use only for tests that need to verify
    {meth}`meta_package_manager.execution.CLIExecutor.run` catches
    {exc}`subprocess.TimeoutExpired` and logs the expected warning.
    """
    return _patch_pool_with(monkeypatch, TimingOutFakeManager())


@fixture
def subcmd():
    """Fixture used in `test_cli_*.py` files to set the subcommand arguments in all
    CLI calls.

    Must returns a string or an iterable of strings. Defaults to `None`, which allows
    tests relying on this fixture to selectively skip running.
    """
    return


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
    "asdf": "jq",
    # Declares no install operation: the round-trip auto-skips. bin keys every
    # other operation on the installed binary's absolute path, so that is the
    # shape an identifier takes here.
    "bin": "/usr/local/bin/bin",
    "brew": "nyancat",
    "bun": "cowsay",
    "cargo": "fsays",
    "cask": "itsycal",
    "cave": "base/figlet",
    "choco": "hyperfine",
    "chromebrew": "sl",
    "composer": "ralouphie/getallheaders",
    "conda": "pytz",  # Pure-Python, zero-dependency leaf on the default channel.
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
    "gext": "caffeine@patapon.info",
    # A tiny script-based extension (a bare git clone), from a GitHub CLI maintainer.
    "gh-ext": "mislav/gh-branch",
    # A tool version, which is what ghcup calls a package. `hls` rather than a
    # GHC: every ghcup artifact is a large download, and the language server is
    # among the lighter ones. Pinned so the round-trip does not depend on
    # whatever the current release happens to be.
    "ghcup": "hls-2.9.0.1",
    "guix": "hello",
    "haxelib": "hxjsonast",  # Tiny zero-dependency JSON parser.
    # A channel, which is what juliaup calls a package. An old released series
    # rather than `release`: every Julia is a large download, and removing the
    # channel the host actually uses is what `remove` refuses outright.
    "juliaup": "1.6",
    "krew": "ctx",  # Tiny context-switcher plugin of krew's own index.
    # Declares no install operation: the round-trip auto-skips. lazy.nvim manages
    # itself, so it is a real entry of its own inventory.
    "lazy": "lazy.nvim",
    # Pure-Lua table pretty-printer, one file and no dependencies.
    "luarocks": "inspect",
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
    "pikaur": "nyancat",
    "pip": "pytz",
    "pipx": "pycowsay",
    # conda-forge ships no nyancat, so pixi reuses the binary-store pick. It is a
    # single self-contained Rust binary, built for every platform pixi runs on.
    "pixi": "hyperfine",
    "pkcon": "hello",
    "pkg": "nyancat",
    "pkg-tools": "nyancat",
    "pkgin": "nyancat",
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
    "rustup": "1.60.0",
    "scoop": "main/hyperfine",
    "sdkman": "jbang",
    "sfsu": "main/hyperfine",
    # Declares no install operation: the round-trip auto-skips.
    "sheldon": "zsh-autosuggestions",
    "slapt-get": "nano",
    "snap": "hello-world",
    "soar": "bat",  # Single-file static binary from the soarpkgs registry.
    "sorcery": "figlet",
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
    # Zinit's own do-nothing plugin: an empty repository it documents for
    # ice-only usage, so loading and deleting it runs no third-party code.
    # Declares no install operation: the round-trip auto-skips.
    "zim": "zsh-users/zsh-completions",
    "zinit": "zdharma-continuum/null",
    # Declares no install operation: the round-trip auto-skips.
    "zplug": "zdharma-continuum/null",
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

# Collection of pre-computed parametrized decorators.

all_managers = pytest.mark.parametrize("manager", pool.values(), ids=attrgetter("id"))

all_manager_ids = pytest.mark.parametrize("manager_id", pool.all_manager_ids)
maintained_manager_ids = pytest.mark.parametrize(
    "manager_id",
    pool.maintained_manager_ids,
)
default_manager_ids = pytest.mark.parametrize("manager_id", pool.default_manager_ids)
unsupported_manager_ids = pytest.mark.parametrize(
    "manager_id",
    pool.unsupported_manager_ids,
)

manager_classes_params = pytest.mark.parametrize(
    "manager_class",
    manager_classes,
    ids=attrgetter("name"),
)

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


INSTALL_REMOVE_BLOCKED_WHEN: dict[str, bool | Callable[[], bool]] = {
    # choco installs to an admin-only location the unelevated CI process cannot write to.
    "choco": is_github_ci,
    # cpan writes to the system Perl tree, out of reach only on the x86 Linux runners.
    "cpan": cpan_install_blocked,
    # The RPM and zypper front-ends are not backed by a working RPM/SUSE distro on the
    # Debian-based ubuntu runners (no release version, no repositories), so they cannot
    # even resolve the package and fail before reaching the privileged install step.
    "dnf": is_linux,
    "dnf5": is_linux,
    "yum": is_linux,
    "zypper": is_linux,
    # flatpak has no remote configured to resolve apps from on the runners.
    "flatpak": is_linux,
    # fwupd flashes firmware; the CI VMs expose no flashable hardware, so the install
    # exits non-zero.
    "fwupd": True,
    # gem carries no blocker: RubyGems falls back to a user install when the system
    # gem directory is not writable, so the round-trip completes on every runner,
    # Linux included. The `is_linux` blocker that used to sit here asserted a failure
    # that no longer happens on any image.
    # gh refuses extension installs without credentials; tests.yaml feeds the workflow
    # token to the destructive CI step so this round-trip runs for real there.
    "gh-ext": gh_unauthenticated,
    # mas resolves an install through an App Store search that finds nothing for the
    # numeric id on the headless runners, so the install fails.
    "mas": is_github_ci,
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
    # mpm sudo-escalates snap now (snapd rejects unprivileged state changes), so the
    # blocker turns on whether that sudo runs unattended. A typical Linux host
    # password-gates sudo, failing the non-interactive install; GitHub's Ubuntu runners
    # grant passwordless sudo, so snap completes a real install+remove of hello-world
    # and is not a blocker there.
    "snap": lambda: is_linux() and not is_github_ci(),
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
zero-argument callable evaluated per host: `is_linux` for the unprivileged Linux runner,
`is_github_ci` for GitHub Actions only (a configured local box can still install), or a
live probe like `gh_unauthenticated` when installability hinges on host state rather than
platform. Resolve one through {func}`install_remove_blocked` rather than calling it
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


# Unmaintained managers are excluded: their upstreams are unreliable or gone, so a real
# install/remove would only contribute flakiness (see PackageManager.unmaintained).
maintained_manager_ids_and_dummy_package = pytest.mark.parametrize(
    "manager_id,package_id",
    tuple(param(mid, PACKAGE_IDS[mid], id=mid) for mid in pool.maintained_manager_ids),
)
