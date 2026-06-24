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

from functools import partial
from operator import attrgetter

import pytest

# Pre-load invocation helpers to be used as pytest's fixture.
from click_extra.pytest import create_config, runner  # noqa: F401
from extra_platforms import is_github_ci, is_linux
from extra_platforms.pytest import skip_guix_build
from pytest import fixture, param

from meta_package_manager.cli import mpm
from meta_package_manager.pool import ManagerPool, manager_classes, pool

from .fake_manager import FakeManager, TimingOutFakeManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from _pytest.config import Config


def pytest_addoption(parser):
    """Add custom command line options.

    Based on `Pytest's documentation examples
    <https://docs.pytest.org/en/latest/example/simple.html#control-skipping-of-tests-according-to-command-line-option>`_.

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
    """Apply collection-time skips: destructive-test selection from the command
    line, plus a Guix-build skip for the manager and CLI integration tests."""
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

    # Integration tests drive real package managers (``test_manager_*``) or the
    # ``mpm`` CLI end-to-end (``test_cli*``), neither of which exists in a
    # hermetic build sandbox. Mark them to skip inside a Guix build (detected by
    # ``extra_platforms`` via ``HOME=/homeless-shelter``) so downstream
    # packagers can run the whole suite instead of ignoring entire modules.
    for item in items:
        if item.path.name.startswith(("test_manager_", "test_cli")):
            item.add_marker(skip_guix_build)


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
def isolate_user_config(monkeypatch, tmp_path):
    """Hide the developer's real ``mpm`` configuration from the test suite.

    click-extra derives the default ``--config`` search pattern from
    :func:`click.get_app_dir`, which resolves to the *host* configuration folder
    (``~/Library/Application Support/mpm`` on macOS, ``~/.config/mpm`` on Unix).
    Any ``config.toml`` living there bleeds into every in-process CLI
    invocation: a local ``cpan = false``, for instance, silently drops the
    manager from the default selection, so ``check_manager_selection`` assertions
    that expect the full default set fail locally while passing in CI, which has
    no such file.

    Repointing ``get_app_dir`` at a fresh empty directory makes the suite
    hermetic with respect to the host configuration. Tests that exercise config
    loading pass ``--config <path>`` explicitly, which overrides this default and
    is therefore left untouched.

    .. note::
        Only the in-process config discovery is redirected. ``HOME`` is left
        intact so the integration layer keeps detecting the real package
        managers, and the override does not propagate to subprocesses.
    """
    app_dir = tmp_path / "app-dir"
    app_dir.mkdir()
    monkeypatch.setattr(
        "click_extra.config.option.get_app_dir",
        lambda *args, **kwargs: str(app_dir),
    )


@fixture
def invoke(runner):  # noqa: F811
    yield partial(runner.invoke, mpm)


def _patch_pool_with(monkeypatch, fake):
    """Replace ``pool.select_managers`` with a generator yielding ``fake``.

    Mirrors the runtime knobs (timeout, stop_on_error, dry_run,
    ignore_auto_updates) that
    :py:meth:`meta_package_manager.pool.ManagerPool._select_managers` would
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
    return fake


@fixture
def fake_pool(monkeypatch):
    """Yield a single deterministic :class:`FakeManager` from the pool.

    Use for CLI plumbing tests (stats lines, table rendering, exit codes)
    that need a stable package set regardless of host PATH.
    """
    return _patch_pool_with(monkeypatch, FakeManager())


@fixture
def slow_fake_pool(monkeypatch):
    """Yield a :class:`TimingOutFakeManager` whose ``outdated`` exceeds ``--timeout``.

    Use only for tests that need to verify
    :py:meth:`meta_package_manager.execution.CLIExecutor.run` catches
    :py:exc:`subprocess.TimeoutExpired` and logs the expected warning.
    """
    return _patch_pool_with(monkeypatch, TimingOutFakeManager())


@fixture(scope="class")
def subcmd():
    """Fixture used in ``test_cli_*.py`` files to set the subcommand arguments in all
    CLI calls.

    Must returns a string or an iterable of strings. Defaults to ``None``, which allows
    tests relying on this fixture to selectively skip running.
    """
    return


PACKAGE_IDS = {
    "apk": "nyancat",
    "apm": "markdown-pdf",
    "apt": "nyancat",
    "apt-mint": "nyancat",
    "asdf": "jq",
    "brew": "nyancat",
    "cargo": "fsays",
    "cask": "itsycal",
    "choco": "hyperfine",
    "composer": "ralouphie/getallheaders",
    "cpan": "Try::Tiny",
    "deb-get": "deb-get",
    "dnf": "nyancat",
    "dnf5": "nyancat",
    "emerge": "games-misc/nyancat",
    "eopkg": "sl",
    "flatpak": "org.gnome.Calculator",
    "fwupd": "f95c9218acd12697af946874bfe4239587209232",  # No-op without device.
    "gem": "paint",
    "guix": "hello",
    "macports": "hello",
    "mas": "747648890",  # Telegram (test is always skipped).
    "mise": "jq",
    "nix": "hello",
    "npm": "ms",
    "opkg": "lolcat",
    "pacaur": "nyancat",
    "pacman": "nyancat",
    "paru": "nyancat",
    "pip": "pytz",
    "pipx": "pycowsay",
    "pkg": "nyancat",
    "pnpm": "ms",
    "ports": "net/nyancat",
    "pwsh-gallery": "Posh-Git",
    "scoop": "main/hyperfine",
    "sdkman": "jbang",
    "sfsu": "main/hyperfine",
    "snap": "hello-world",
    "steamcmd": "1007",  # Steamworks SDK Redist.
    "stew": "sharkdp/hyperfine",
    "topgrade": "topgrade",
    "uv": "pytz",
    "uvx": "pycowsay",
    "vscode": "tamasfe.even-better-toml",
    "vscodium": "tamasfe.even-better-toml",
    "winget": "sharkdp.hyperfine",
    "xbps": "sl",
    "yarn": "ms",
    "yarn-berry": "ms",
    "pacstall": "hello",
    "yay": "nyancat",
    "yum": "nyancat",
    "zerobrew": "nyancat",
    "zypper": "nyancat",
}
"""Package IDs used by the destructive install/remove tests, one per manager.

Each entry is fed to ``mpm --<manager_id> install <package_id>`` immediately followed
by ``mpm --<manager_id> remove <package_id>``, so the package is both added to and
removed from the host running the test. Each ID is picked to keep that round-trip cheap
and free of side effects:

- Tiny and quick to install, with no dependency tree, no services or daemons, and no
  ``/etc`` configuration: just a self-contained binary.
- Not a tool the OS, the manager itself, or common scripts are likely to depend on.
  Ubiquitous utilities (``wget``, ``curl``, ``git``, ``jq``, ...) are avoided: they are
  usually already installed (so the install step is a no-op) and removing them can break
  the host.
- Preferably from the Rust or Go ecosystems, which rarely pull in extra dependencies.

Wherever a manager exposes general-purpose binaries the same low-impact tools are reused
for consistency: ``nyancat`` (a single-file C binary packaged by nearly every Linux
distro, Homebrew and FreeBSD as ``net/nyancat``), GNU ``hello`` for the functional
managers (Guix, Nix) and ``hyperfine`` for the Windows binary stores and ``stew``.
Distros that lack ``nyancat`` fall back to ``sl`` (Solus, Void) or ``lolcat`` (OpenWrt).
Language and application managers use the smallest inert package native to their
ecosystem (``ms`` for npm and Yarn, ``pycowsay`` for the pipx-style installers that
require a console-script entry point, ...).

.. warning::

    ``fwupd`` flashes real firmware. Its ID is a release with no matching device on CI
    runners, where the install is therefore a no-op. Never run the destructive ``fwupd``
    test on hardware that the ID actually targets.

.. note::

    A few managers cannot offer a small binary: ``sdkman`` only ships full SDKs
    (``jbang`` is its lightest candidate), and ``mas`` needs a signed App Store app (its
    test is skipped anyway). ``deb-get`` and ``topgrade`` have no real per-package
    install, so they reference themselves.

Only to be used for destructive tests.
"""

assert set(PACKAGE_IDS) == set(pool.all_manager_ids)

# Collection of pre-computed parametrized decorators.

all_managers = pytest.mark.parametrize("manager", pool.values(), ids=attrgetter("id"))
available_managers = pytest.mark.parametrize(
    "manager",
    tuple(m for m in pool.values() if m.available),
    ids=attrgetter("id"),
)

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

manager_classes = pytest.mark.parametrize(  # type: ignore[assignment]
    "manager_class",
    manager_classes,
    ids=attrgetter("name"),
)

SHORT_FAILURE_TIMEOUT = 10
"""Seconds to cap a destructive install that is *expected* to fail.

The managers in :py:data:`INSTALL_REMOVE_BLOCKERS` cannot complete a real install in the
test environment. Most fail within a second (a permission error, a missing remote, an
empty search), but a few (``scoop`` and ``sfsu`` on Windows, ``pwsh-gallery`` on macOS)
hang with no error until the state-change timeout would otherwise elapse. Capping their
CLI calls keeps the doomed attempts cheap: long enough for the fast failures to surface,
short enough that the genuine hangs do not dominate the destructive job's wall-clock.
"""

INSTALL_REMOVE_BLOCKERS: dict[str, Callable[[], bool]] = {
    # choco installs to an admin-only location the unelevated CI process cannot write to.
    "choco": is_github_ci,
    # cpan writes to the system Perl tree, unwritable by the unelevated Linux user.
    "cpan": is_linux,
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
    "fwupd": lambda: True,
    # gem writes to the system gem directory, unwritable by the unelevated Linux user.
    "gem": is_linux,
    # mas resolves an install through an App Store search that finds nothing for the
    # numeric id on the headless runners, so the install fails.
    "mas": is_github_ci,
    # pnpm add --global needs a PNPM_HOME (from `pnpm setup`) the runners do not set up.
    "pnpm": is_github_ci,
    # pwsh-gallery's PSResourceGet lookup is unreliable on the runners: Find-PSResource
    # hangs on the macOS image and returns a case-mismatched name on Linux, so the install
    # never resolves the package.
    "pwsh-gallery": is_github_ci,
    # scoop install hangs until the timeout on the GitHub Windows runners; sfsu wraps it.
    "scoop": is_github_ci,
    "sfsu": is_github_ci,
    # snap install requires root; mpm does not elevate, so it fails as the test user.
    "snap": is_linux,
    # steamcmd can only install titles owned by an authenticated account; the runners'
    # anonymous session is not logged in, so the install fails. No environment satisfies it.
    "steamcmd": lambda: True,
}
"""Managers that cannot complete a real install in a given environment, mapped to the
predicate that is True where the manager is known to be uninstallable.

Rather than skip these managers (which would also drop their dispatch coverage and any
signal that they still fail the *expected* way), the destructive install/remove test drives
each one's ``install`` anyway, caps the doomed CLI call with
:py:data:`SHORT_FAILURE_TIMEOUT`, and asserts that mpm reports the stable failure: exit code
``1`` and a ``Could not install: {package}`` critical message. The follow-up ``remove`` is
skipped, since the failed install left nothing to remove and the working managers already
cover the removal path.

The predicate is a zero-argument callable: ``is_linux`` for the unprivileged Linux runner,
``is_github_ci`` for GitHub Actions only (a configured local box can still install), or
``lambda: True`` for managers no environment can install.

.. note::

    The assertion deliberately targets mpm's own ``Could not install:`` message rather than
    the underlying tool's error. The raw tool output is not a stable contract: it is
    platform-specific (``pwsh-gallery`` times out on macOS but hits a name-case mismatch on
    Linux), stage-specific (``dnf``/``zypper``/``flatpak`` fail at the search step, never
    reaching their privileged install errors), and drifts across tool versions, OS images,
    and locales. mpm's failure message is identical everywhere, so the test stays robust.
"""

# Deprecated managers are excluded: their upstreams are unreliable or gone, so a real
# install/remove would only contribute flakiness (see PackageManager.deprecated).
maintained_manager_ids_and_dummy_package = pytest.mark.parametrize(
    "manager_id,package_id",
    tuple(param(mid, PACKAGE_IDS[mid], id=mid) for mid in pool.maintained_manager_ids),
)
