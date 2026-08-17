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

import sys
from functools import partial
from operator import attrgetter
from pathlib import Path

import pytest

# Shared version-gated TOML reader, re-exported for the whole test suite.
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]  # noqa: F401

# Pre-load invocation helpers to be used as pytest's fixture.
from click_extra.pytest import create_config, runner  # noqa: F401
from extra_platforms.pytest import skip_hermetic_build
from pytest import fixture

from meta_package_manager.cli import mpm
from meta_package_manager.pool import ManagerPool, manager_classes, pool

from .destructive_plan import destructive_group
from .fake_manager import FakeManager, TimingOutFakeManager

TYPE_CHECKING = False
if TYPE_CHECKING:
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
        "destructive_all_managers: mark a destructive test as driving every "
        "available manager in one invocation, which no lock-family grouping "
        "can isolate: CI runs these on their own, sequentially, after the "
        "parallel destructive step.",
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
    https://mpm.run/packaging/
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

    # Give every destructive test its scheduling group, so the destructive CI
    # step can run `--dist=loadgroup` without two workers racing one package
    # manager, one backend lock, or one install target: tests sharing a group
    # serialize on a single worker, while groups spread across workers. The
    # cross-manager tests drive every available manager in one invocation, so
    # no grouping can isolate them: they carry `destructive_all_managers` and
    # run in a sequential CI step of their own.
    violations = []
    for item in items:
        all_managers = "destructive_all_managers" in item.keywords
        if all_managers and "destructive" not in item.keywords:
            # The marker only makes sense on a destructive test: anything else
            # would smuggle a cross-manager mutation into the parallel
            # non-destructive slice.
            violations.append(item.nodeid)
            continue
        if all_managers or "destructive" not in item.keywords:
            continue
        # An explicit group (from a test hardcoding its manager) wins.
        if item.get_closest_marker("xdist_group"):
            continue
        callspec = getattr(item, "callspec", None)
        manager_id = callspec.params.get("manager_id") if callspec else None
        if manager_id is None:
            violations.append(item.nodeid)
            continue
        item.add_marker(pytest.mark.xdist_group(name=destructive_group(manager_id)))
    if violations:
        msg = (
            "Every destructive test needs a scheduling group: parametrize it "
            "with manager_id, mark it with an explicit xdist_group, or mark "
            "it (and only a destructive test) with destructive_all_managers. "
            "Offenders: " + ", ".join(sorted(violations))
        )
        raise pytest.UsageError(msg)


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


@fixture(autouse=True, scope="session")
def warm_manager_probes():
    """Resolve every pool manager's availability before the first test runs.

    The pool is a module-global singleton shared by every test of the process,
    and a manager's version probe caches its first result on the instance. The
    click-extra `runner` fixture pins `HOME` (and its platform equivalents) to
    an empty directory for the duration of each CLI invocation, so a probe
    first fired from inside a test spawns into a crippled environment: the
    GitHub runners' rustup shim at `~/.cargo/bin/cargo`, for one, cannot
    resolve a toolchain without `$HOME/.rustup` and answers with an error
    instead of a version, caching cargo as unavailable for every later test
    on that worker. Warming the whole pool here, before any test and outside
    any runner isolation, seeds those caches from the real environment.

    test_pool.py's selection cases used to provide this warming as an accident
    of materializing their expected manager lists at import time, until
    probing at collection made xdist workers' collected parametrize lists
    diverge. A session fixture runs after collection, so workers still agree
    on the test list, and once per worker, so the cost matches what
    collection-time probing already paid.

    The probes run sequentially on purpose, and not through
    {func}`~meta_package_manager.dispatch.warm_availability`: that helper
    sizes its thread pool from the active click context, of which a pytest
    session has none, so it returns before probing anything.
    """
    for manager in pool.values():
        manager.available


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

