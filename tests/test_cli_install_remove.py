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
"""`mpm install` and `mpm remove` CLI tests.

The two operations are siblings, so they share one module.
"""

from __future__ import annotations

import json
import re
from functools import partial

import pytest
from boltons.strutils import strip_ansi
from extra_platforms import is_windows

from meta_package_manager.execution import CLIError
from meta_package_manager.manager import CooldownHold
from meta_package_manager.pool import pool
from meta_package_manager.sudo import UNANSWERED_PROMPT_DETAIL
from meta_package_manager.tables import PackageOutcome

from . import conftest
from .destructive_plan import (
    REMOVE_REFUSES_INSTALLED,
    SHORT_FAILURE_TIMEOUT,
    install_remove_blocked,
    maintained_manager_ids_and_dummy_package,
)
from .fake_manager import ChangingFakeManager
from .test_cli import (
    assert_no_manager_selected,
    check_manager_selection,
    check_report,
)


class SearchlessFakeManager(ChangingFakeManager):
    """A changing fake with no search operation."""

    def search(self, query, extended, exact):
        raise NotImplementedError


class UnsearchableFakeManager(ChangingFakeManager):
    """A changing fake whose search command fails."""

    def search(self, query, extended, exact):
        raise CLIError(1, "", "Index unreachable.")


class HeldFakeManager(ChangingFakeManager):
    """A changing fake whose packages the cooldown holds back."""

    def cooldown_hold(self, package_id):
        return CooldownHold()


@pytest.fixture
def subcmd():
    return "install", "arrow"


def evaluate_signals(mid, stdout, stderr):
    yield from (
        # install announces the managers it will try, in priority order.
        bool(
            re.search(
                rf"Installation priority:.*\b{mid}\b",
                stderr,
            ),
        ),
        # remove dispatches to each manager that has the package installed.
        bool(
            re.search(
                rf"Remove \S+ with\b.*\b{mid}\b",
                stderr,
            ),
        ),
    )


check_selection = partial(check_manager_selection, signals=evaluate_signals)
"""Selection assertions reading this subcommand's own signals."""


@pytest.mark.parametrize("operation", ("install", "remove"))
def test_no_package_id(invoke, operation):
    result = invoke(operation)
    assert result.exit_code == 2
    assert not result.stdout
    assert "Error: Missing argument 'PACKAGES_SPECS...'." in result.stderr


def test_install_unresolved_exits_nonzero(invoke, fake_pool):
    """install exits non-zero when no manager can provide the requested package.

    Guards against a regression where a failed install was swallowed and the
    command still exited `0` (see the `install` command in `cli.py`).
    """
    result = invoke("install", "package-provided-by-no-manager")
    assert result.exit_code == 1


@pytest.mark.parametrize("flag", ("--zero-exit", "-0"))
def test_install_unresolved_zero_exit_opt_out(invoke, fake_pool, flag):
    """-0/--zero-exit keeps the exit code at 0 on per-package failures.

    The critical summary stays as the durable record.
    """
    result = invoke(flag, "install", "package-provided-by-no-manager")
    assert result.exit_code == 0
    assert "Could not install: package-provided-by-no-manager." in result.stderr


def test_remove_absent_package_is_idempotent(invoke, fake_pool):
    """Removing a package no manager has installed is a no-op, not a failure.

    `remove` only fails when a manager that *has* the package fails to remove it.
    """
    result = invoke("remove", "package-installed-by-no-manager")
    assert result.exit_code == 0


@pytest.mark.skipif(is_windows(), reason="sheldon runs on Linux and macOS alone")
def test_remove_with_manager_lacking_inventory(invoke, create_config, tmp_path):
    """A package handed to a lone manager keeping no inventory reaches its `remove`.

    `sheldon` implements `remove` but no `installed`, so no lookup can find a package
    in it. The lookup selecting the managers implementing `installed` exited the
    command on its empty selection, and past that the package was skipped as
    unrecognized.
    """
    fake_sheldon = tmp_path / "sheldon"
    fake_sheldon.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        '  --version) echo "sheldon 0.8.5";;\n'
        '  remove) echo "removed $2";;\n'
        "esac\n",
        encoding="UTF-8",
    )
    fake_sheldon.chmod(0o755)
    conf_path = create_config(
        "conf.toml",
        f"""
        [mpm.overrides.sheldon]
        cli_search_path = ["{tmp_path}"]
        """,
    )
    result = invoke(
        "--config", str(conf_path), "--sheldon", "remove", "zsh-autosuggestions"
    )
    assert result.exit_code == 0
    assert "✓ sheldon.remove: zsh-autosuggestions" in strip_ansi(result.stderr)


def test_install_reports_what_moved(invoke, changing_fake_pool):
    """A package tied to its manager installs on the concurrent path.

    The report names it with the dependency it pulled in.
    """
    mid = changing_fake_pool.id
    result = invoke("install", f"pkg:{mid}/fake-pkg-theta")
    assert result.exit_code == 0
    assert f"✓ {mid}.install: fake-pkg-theta" in strip_ansi(result.stderr)
    check_report(
        result.stdout,
        {
            "fake-pkg-gamma": ("0.1.0", PackageOutcome.INSTALLED.label),
            "fake-pkg-theta": ("1.0.0", PackageOutcome.INSTALLED.label),
        },
    )


def test_install_untied_reports_every_attempt(invoke, changing_fake_pool):
    """Packages left untied install through the sequential priority search.

    Its manager opens once, so the report keeps the first install too.
    """
    result = invoke("install", "fake-pkg-theta", "fake-pkg-iota")
    assert result.exit_code == 0
    check_report(
        result.stdout,
        {
            "fake-pkg-gamma": ("0.1.0", PackageOutcome.INSTALLED.label),
            "fake-pkg-iota": ("1.0.0", PackageOutcome.INSTALLED.label),
            "fake-pkg-theta": ("1.0.0", PackageOutcome.INSTALLED.label),
        },
    )


@pytest.mark.parametrize(
    "detail",
    (
        pytest.param(UNANSWERED_PROMPT_DETAIL, id="known-cause"),
        pytest.param(None, id="plain-failure"),
    ),
)
@pytest.mark.parametrize(
    "spec",
    (
        pytest.param("pkg:{mid}/fake-pkg-theta", id="tied"),
        pytest.param("fake-pkg-theta", id="untied"),
    ),
)
def test_failed_install_names_its_cause_on_the_trail(
    invoke, changing_fake_pool, monkeypatch, spec, detail
):
    """The `✘` line of a failed install names the cause its error carries.

    Both install paths do: the concurrent one a tied package takes, and the
    sequential priority search of an untied one. A failure with no known cause
    keeps a bare line, the glyph saying enough.
    """
    mid = changing_fake_pool.id

    def failing_install(manager, package_id, version=None):
        # Recorded then raised, as the failure gate of `run()` does.
        error = CLIError(None, "", "Timed out after 500s.", detail)
        manager.cli_errors.append(error)
        raise error

    monkeypatch.setattr(ChangingFakeManager, "install", failing_install)
    result = invoke("install", spec.format(mid=mid))
    assert result.exit_code == 1
    stderr = strip_ansi(result.stderr)
    line = f"✘ {mid}.install: fake-pkg-theta"
    assert line in stderr
    assert (f"{line} ({UNANSWERED_PROMPT_DETAIL})" in stderr) is bool(detail)


def test_dry_run_install_names_plan(invoke, changing_fake_pool, queries_through_a_cli):
    """A simulated search finds nothing, which is no proof the package is missing."""
    mid = changing_fake_pool.id
    result = invoke("--dry-run", "install", "fake-pkg-theta")
    stderr = strip_ansi(result.stderr)
    assert f"✘ {mid}.install: fake-pkg-theta (dry-run)" in stderr
    assert "Run with --plan to resolve it." in stderr


def test_plan_install_resolves_what_dry_run_cannot(
    invoke, changing_fake_pool, queries_through_a_cli
):
    """The control: `--plan` runs the search, so the same package resolves."""
    mid = changing_fake_pool.id
    result = invoke("--plan", "install", "fake-pkg-theta")
    stderr = strip_ansi(result.stderr)
    assert result.exit_code == 0
    assert f"✓ {mid}.install: fake-pkg-theta" in stderr
    assert "Run with --plan" not in stderr


def test_install_report_serialized_keeps_the_exit_code(invoke, changing_fake_pool):
    """The serialized report prints, and a failed package still exits non-zero."""
    mid = changing_fake_pool.id
    result = invoke(
        "--table-format",
        "json",
        "install",
        f"pkg:{mid}/fake-pkg-theta",
        f"pkg:{mid}/fake-pkg-broken",
    )
    assert result.exit_code == 1
    assert "Could not install: fake-pkg-broken." in result.stderr
    packages = json.loads(result.stdout)[mid]["packages"]
    assert [(p["id"], p["status"]) for p in packages] == [
        ("fake-pkg-gamma", "installed"),
        ("fake-pkg-theta", "installed"),
    ]


def test_install_ties_and_searches_in_one_run(invoke, changing_fake_pool):
    """A run holding both kinds installs the tied package first.

    Then it searches for the untied one.
    """
    mid = changing_fake_pool.id
    result = invoke("install", f"pkg:{mid}/fake-pkg-theta", "fake-pkg-iota")
    assert result.exit_code == 0
    stderr = strip_ansi(result.stderr)
    assert stderr.index(f"✓ {mid}.install: fake-pkg-theta") < stderr.index(
        f"✓ {mid}.install: fake-pkg-iota"
    )
    check_report(
        result.stdout,
        {
            "fake-pkg-gamma": ("0.1.0", PackageOutcome.INSTALLED.label),
            "fake-pkg-iota": ("1.0.0", PackageOutcome.INSTALLED.label),
            "fake-pkg-theta": ("1.0.0", PackageOutcome.INSTALLED.label),
        },
    )


def test_install_without_search_tries_the_package_directly(invoke, patch_pool_with):
    """A manager with no search operation still gets the install attempt.

    The next manager never runs.
    """
    patch_pool_with(SearchlessFakeManager(), ChangingFakeManager())
    result = invoke("--verbosity", "INFO", "install", "fake-pkg-theta")
    assert result.exit_code == 0
    stderr = strip_ansi(result.stderr)
    assert "fake-pkg-theta existence unconfirmed, try to directly install it..." in (
        stderr
    )
    assert "✓ searchlessfakemanager.install: fake-pkg-theta" in stderr
    assert "changingfakemanager.install" not in stderr


def test_install_falls_through_a_failed_search(invoke, patch_pool_with):
    """A search that fails counts as a miss: the next manager gets its turn."""
    patch_pool_with(UnsearchableFakeManager(), ChangingFakeManager())
    result = invoke("install", "fake-pkg-theta")
    assert result.exit_code == 0
    stderr = strip_ansi(result.stderr)
    assert "✘ unsearchablefakemanager.install: fake-pkg-theta (not found)" in stderr
    assert "✓ changingfakemanager.install: fake-pkg-theta" in stderr


def test_install_stops_at_a_cooldown_hold(invoke, patch_pool_with):
    """A held package ends the search at the first manager providing it.

    The next manager would sidestep the hold. A hold is no failure, so the run exits
    `0`.
    """
    patch_pool_with(HeldFakeManager(), ChangingFakeManager())
    result = invoke("install", "fake-pkg-theta")
    assert result.exit_code == 0
    stderr = strip_ansi(result.stderr)
    assert (
        "Hold fake-pkg-theta: its latest release cannot be dated (fail-closed)."
    ) in stderr
    assert "✘ heldfakemanager.install: fake-pkg-theta (cooldown)" in stderr
    assert "changingfakemanager.install" not in stderr


def test_install_refuses_an_ambiguous_exact_search(
    invoke, changing_fake_pool, monkeypatch
):
    """An exact search answering two packages stops the install.

    It is a bug of the manager, and the install does not pick one of them.
    """

    def search(manager, query, extended, exact):
        yield manager.package(id=query, latest_version="1.0.0")
        yield manager.package(id=query, latest_version="2.0.0")

    monkeypatch.setattr(ChangingFakeManager, "search", search)
    result = invoke("install", "fake-pkg-theta")
    assert isinstance(result.exception, ValueError)
    assert str(result.exception) == "Exact search returned multiple packages."


@pytest.mark.parametrize(
    ("args", "removed"),
    (
        ((), {"fake-pkg-delta": "4.0.0"}),
        (("--orphans",), {"fake-pkg-delta": "4.0.0", "fake-pkg-epsilon": "5.2.0"}),
    ),
)
def test_remove_reports_what_moved(invoke, changing_fake_pool, args, removed):
    """The report names the removed package, and the orphan its cascade took."""
    result = invoke("remove", *args, "fake-pkg-delta")
    assert result.exit_code == 0
    check_report(
        result.stdout,
        {
            package_id: (version, PackageOutcome.REMOVED.label)
            for package_id, version in removed.items()
        },
    )


@pytest.mark.destructive()
@maintained_manager_ids_and_dummy_package
def test_single_manager_install_and_remove(invoke, manager_id, package_id):
    """Test the installation and removal of a package with each manager.

    ```{caution}

    `strict_selection_match` is set to `False` because the `install`
    subcommand will not try all managers selected by default. So a strict
    match is not possible.

    That's because `install` subcommand try each user-selected manager until
    it find one providing the package we seek to install, after which the
    process stop.
    ```

    ```{note}

    Managers that cannot complete a real install in a given environment are not skipped:
    they are listed in `INSTALL_REMOVE_BLOCKED_WHEN` (`destructive_plan.py`) and driven
    anyway. The blocked `install` is capped at `SHORT_FAILURE_TIMEOUT` and asserted to
    fail the stable mpm way (exit `1` plus a ``Could not install:` message). It runs at
    `--verbosity INFO``: the minimum level at which the `Installation priority` dispatch
    signal is visible (the default `WARNING` would hide it and make
    {meth}`~tests.test_cli.check_manager_selection` pass vacuously). No follow-up
    `remove`: the failed install left nothing to remove, and the working managers
    already cover the removal path.

    A manager in `REMOVE_REFUSES_INSTALLED` is the other way round: its
    install succeeds and its `remove` is refused on purpose, so both legs
    run and the refusal is asserted rather than a clean exit.
    ```
    """
    if install_remove_blocked(manager_id):
        # This manager cannot complete a real install here. Drive the doomed install
        # anyway, capped at SHORT_FAILURE_TIMEOUT, and assert it fails the stable mpm
        # way. No remove leg: the failed install left nothing to remove, and the
        # working managers below already cover the removal path.
        result = invoke(
            f"--{manager_id}",
            "--verbosity",
            "INFO",
            "--timeout",
            str(SHORT_FAILURE_TIMEOUT),
            "install",
            package_id,
        )
        # The manager is not available on this host: mpm selected nothing. This
        # supersedes the blocker expectation, which only applies once the manager is
        # present and reaches its (doomed) install.
        if result.exit_code == 2:
            assert_no_manager_selected(result)
            return
        assert result.exit_code == 1
        assert f"Could not install: {package_id}" in result.stderr, (
            f"{manager_id} install: expected a 'Could not install:' failure in "
            f"stderr, got:\n{result.stderr}"
        )
        check_selection(
            result,
            {manager_id},
            reference_set=pool.all_manager_ids,
            strict_selection_match=False,
        )
        return

    for command in ("install", "remove"):
        result = invoke(f"--{manager_id}", command, package_id)

        # The manager is not available on this host: mpm selected nothing.
        if result.exit_code == 2:
            assert_no_manager_selected(result)
            continue

        # This manager refuses to remove the package the install leg just placed
        # (see REMOVE_REFUSES_INSTALLED). Assert the stable mpm failure rather
        # than a clean exit, so the expected refusal stays a signal.
        if command == "remove" and manager_id in REMOVE_REFUSES_INSTALLED:
            assert result.exit_code == 1
            assert f"Could not remove: {package_id}" in result.stderr, (
                f"{manager_id} remove: expected a 'Could not remove:' failure in "
                f"stderr, got:\n{result.stderr}"
            )
            continue

        # These installs read a live registry (crates.io, Packagist, the Anaconda
        # channels, CPAN, npm, the snap store, the winget community source) and
        # need a healthy toolchain behind it, so they regularly surface transient
        # failures on the CI runners. A stalled Packagist holds the `composer
        # search` an install starts with past its 120s timeout on every runner at
        # once, and the install then reports its package as not found. conda's
        # solver times out or fails to resolve on the Windows runner. Part of the
        # Windows fleet ships a Strawberry Perl whose CPAN is configured for its
        # SQLite index without DBD::SQLite installed, so every install dies on
        # "install_driver(SQLite) failed". One slow or reset answer from the npm
        # registry fails `npm`, `yarn` and `yarn-berry` alike, since all three
        # read it. And the snap store truncates a download mid-flight as
        # `unexpected EOF`, which the same store does to this workflow's own
        # `snap install` setup steps. Accept exit 1 like
        # test_single_manager_upgrade_all does for the same reason; the
        # check_manager_selection below still asserts mpm dispatched to the
        # manager.
        if manager_id in {
            "cargo",
            "composer",
            "conda",
            "cpan",
            "npm",
            "snap",
            "winget",
            "yarn",
            "yarn-berry",
        }:
            assert result.exit_code in (0, 1)
        else:
            assert result.exit_code == 0
        check_selection(
            result,
            {manager_id},
            reference_set=pool.all_manager_ids,
            strict_selection_match=False,
        )


def test_collection_hook_runs_before_xdist_stamps_the_group():
    """mpm's collection hook must run before xdist's, or the groups do nothing.

    `--dist=loadgroup` does not read the `xdist_group` marker when it schedules:
    xdist's own worker-side hook copies the group name onto the *node id* as an
    `@<group>` suffix, and the controller schedules from that. So a marker this
    suite adds in `pytest_collection_modifyitems` is only seen if that hook has
    already run when xdist's does, and pytest calls the later-registered plugin
    first: the worker interactor registers after `conftest.py`, so without
    `tryfirst` it stamps ids that carry no group at all.

    The failure is silent and platform-shaped, which is why it is guarded here
    rather than left to CI: nothing errors, the tests simply scatter across
    workers, and the only symptom is two managers colliding on a backend lock
    they were supposed to take in turn. `apt` and `aptitude` did exactly that on
    the Ubuntu runners, each reporting the other's process holding
    `/var/lib/dpkg/lock-frontend`.
    """
    opts = getattr(conftest.pytest_collection_modifyitems, "pytest_impl", None)
    assert opts is not None, (
        "the collection hook lost its @pytest.hookimpl decorator, so xdist "
        "stamps node ids before the xdist_group markers exist"
    )
    assert opts["tryfirst"] is True, (
        "the collection hook must keep tryfirst=True: xdist's worker-side hook "
        "would otherwise stamp node ids before the xdist_group markers are added"
    )
