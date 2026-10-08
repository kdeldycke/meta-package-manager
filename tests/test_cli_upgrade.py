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
"""`mpm upgrade` CLI tests.

```{danger}
All tests here must be marked as destructive unless the `--dry-run` parameter is
passed.
```
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from functools import partial

import pytest
from boltons.strutils import strip_ansi

from meta_package_manager.capabilities import Operations
from meta_package_manager.cli import outcome_detail, package_outcomes
from meta_package_manager.cli_maintenance import SWEEP_RESULTS, UPGRADE_RESULTS
from meta_package_manager.dispatch import _LOCK_FAMILY_BY_MANAGER, LockFamily
from meta_package_manager.execution import CLIError
from meta_package_manager.manager import CooldownHold
from meta_package_manager.package import Package
from meta_package_manager.pool import pool
from meta_package_manager.tables import PACKAGE_OUTCOME_GLYPHS, PackageOutcome

from .conftest import default_manager_ids
from .destructive_plan import SHORT_FAILURE_TIMEOUT, upgrade_all_blocked
from .fake_manager import ChangingFakeManager, FakeManager
from .test_cli import (
    assert_no_manager_selected,
    check_manager_selection,
    check_report,
)


@pytest.fixture
def failing_installed_query(monkeypatch):
    """Break `FakeManager.installed`, like a misconfigured `pnpm` breaks its own."""

    def raise_cli_error(manager):
        raise CLIError(1, "", "Global bin directory is not in PATH.")

    monkeypatch.setattr(FakeManager, "installed", property(raise_cli_error))


@pytest.fixture
def subcmd():
    return "upgrade", "--all"


def evaluate_signals(mid, stdout, stderr):
    yield from (
        # The glued `:<mid>:` label form matches whatever level the
        # message lands at: demoted to DEBUG for implicit selection,
        # WARNING/INFO for explicit ones (`mpm --<mid> upgrade`).
        f":{mid}: Does not implement upgrade_all_cli." in stderr,
        f":{mid}: Does not implement {Operations.upgrade_all}." in stderr,
        f":{mid}.upgrade_all: Upgrade all outdated packages." in stderr,
        bool(re.search(rf"Upgrade \S+ with\b.*\b{mid}\b", stderr)),
        f":{mid}: Skipped:" in stderr,
    )


check_selection = partial(check_manager_selection, signals=evaluate_signals)
"""Selection assertions reading this subcommand's own signals."""


@pytest.mark.parametrize("all_option", ("--all", None))
def test_all_managers_dry_run_upgrade_all(invoke, all_option):
    # `--verbosity DEBUG` makes the per-manager skip/does-not-implement
    # messages reach stderr: at default verbosity they stay quiet because
    # this invocation makes no explicit `--<id>` selection.
    result = invoke("--verbosity", "DEBUG", "--dry-run", "upgrade", all_option)
    assert result.exit_code == 0
    if not all_option:
        assert "assume -A/--all option" in result.stderr
    check_selection(result)


@pytest.mark.destructive()
@pytest.mark.destructive_all_managers()
def test_all_managers_upgrade_all(invoke, monkeypatch):
    # Only the explicit `--all` spelling runs destructively: the bare
    # `upgrade` alias is already asserted by both dry-run variants above,
    # and the non-convergent managers (gem re-walks every installed gem
    # even when current) repeat their full upgrade on a second pass,
    # doubling the destructive wall-clock for the sake of an
    # argument-parsing message.
    #
    # Every default manager is selected explicitly because both halves of
    # this test hang on the verbosity mechanics: select_managers demotes
    # the per-manager skip/announce signals to DEBUG on an implicit run,
    # and DEBUG collapses the fan-out to a single worker (serial_at_debug
    # in effective_jobs), which no --jobs value can override. Explicit
    # selection keeps every signal visible at INFO, where the grouped
    # concurrent dispatch engages: this is the one destructive exercise of
    # the concurrent `upgrade --all` path.
    #
    # A manager in UPGRADE_ALL_BLOCKED_WHEN would hold the run until the
    # mutating timeout, so its CLI calls are capped the way an
    # `[mpm.overrides.<id>] timeout` entry caps them.
    capped = [mid for mid in pool.default_manager_ids if upgrade_all_blocked(mid)]
    for mid in capped:
        monkeypatch.setattr(pool[mid], "timeout", SHORT_FAILURE_TIMEOUT)
        monkeypatch.setitem(
            pool.overridden_fields,
            mid,
            {*pool.overridden_fields.get(mid, ()), "timeout"},
        )
    result = invoke(
        *(f"--{mid}" for mid in pool.default_manager_ids),
        "--verbosity",
        "INFO",
        "upgrade",
        "--all",
    )
    # Accept exit code 1: end-to-end destructive upgrades depend on the
    # health of every installed third-party manager, and CI runners
    # regularly surface transient backend failures (missing project files,
    # toolchain gaps, network blips). The contract we test here is that
    # mpm dispatched to every selected manager and surfaced their output.
    assert result.exit_code in (0, 1)
    check_selection(result)
    timed_out = f"Timed out after {SHORT_FAILURE_TIMEOUT}s."
    for mid in capped:
        if f":{mid}.upgrade_all: Upgrade all outdated packages." in result.stderr:
            assert f":{mid}.upgrade_all: {timed_out}" in result.stderr


@default_manager_ids
@pytest.mark.parametrize("all_option", ("--all", None))
def test_single_manager_dry_run_upgrade_all(invoke, manager_id, all_option):
    result = invoke(
        f"--{manager_id}", "--dry-run", "--verbosity", "INFO", "upgrade", all_option
    )
    if not all_option:
        assert "assume -A/--all option" in result.stderr
    if result.exit_code == 2:
        assert_no_manager_selected(result)
    else:
        # Accept exit code 1: some managers (like pip on Windows) may
        # report errors during the upgrade dry-run simulation, causing
        # exit code 1 rather than 0. This is an environmental issue and
        # not a test-logic failure.
        assert result.exit_code in (0, 1)
        check_selection(result, {manager_id})


@pytest.mark.destructive()
@default_manager_ids
def test_single_manager_upgrade_all(invoke, manager_id):
    # Only the explicit `--all` spelling runs destructively: see
    # test_all_managers_upgrade_all.
    # A manager in UPGRADE_ALL_BLOCKED_WHEN cannot finish before the mutating
    # timeout: cap its calls and assert mpm reports the timeout instead.
    blocked = upgrade_all_blocked(manager_id)
    cap = ("--timeout", str(SHORT_FAILURE_TIMEOUT)) if blocked else ()
    result = invoke(f"--{manager_id}", "--verbosity", "INFO", *cap, "upgrade", "--all")
    if result.exit_code == 2:
        assert_no_manager_selected(result)
        return
    # Accept exit code 1: see test_all_managers_upgrade_all.
    assert result.exit_code in (0, 1)
    check_selection(result, {manager_id})
    if blocked:
        timed_out = f"Timed out after {SHORT_FAILURE_TIMEOUT}s."
        assert f":{manager_id}.upgrade_all: {timed_out}" in result.stderr


def test_installed_ids_tolerates_a_failing_cli(
    fake_pool, failing_installed_query, caplog
):
    """A manager whose `installed` CLI fails reports no IDs instead of raising."""
    with caplog.at_level(logging.WARNING):
        assert fake_pool.installed_ids == frozenset()
    assert "Could not list installed packages." in caplog.text


# `upgrade <packages>` and `remove` share the `_dispatch_sourced_operation` engine,
# which reads `installed_ids` on every selected manager to find which ones carry an
# untied package. A manager whose query CLI is broken used to abort the whole command
# with a traceback before the managers that do have the package were ever tried.
@pytest.mark.parametrize("subcommand", ("upgrade", "remove"))
def test_sourcing_survives_a_failing_manager(
    invoke, fake_pool, failing_installed_query, subcommand
):
    result = invoke("--dry-run", subcommand, "fake-pkg-alpha")
    assert result.exit_code == 0
    assert "Traceback" not in result.stderr
    listing_failure = f":{fake_pool.id}.installed: Could not list installed packages."
    assert listing_failure in result.stderr
    # No manager could source the package, so it is skipped rather than fatal.
    assert "fake-pkg-alpha is not recognized" in result.stderr


@pytest.mark.parametrize("subcommand", ("upgrade", "remove"))
def test_dry_run_names_plan_to_resolve_a_package(
    invoke, changing_fake_pool, queries_through_a_cli, subcommand
):
    """`--dry-run` also simulates the listing that ties a package to its manager."""
    result = invoke("--dry-run", subcommand, "fake-pkg-alpha")
    stderr = strip_ansi(result.stderr)
    assert "fake-pkg-alpha is not recognized by any of the selected managers." in stderr
    assert "Run with --plan to resolve it." in stderr


@pytest.mark.parametrize("subcommand", ("upgrade", "remove"))
def test_plan_resolves_a_package_dry_run_cannot(
    invoke, changing_fake_pool, queries_through_a_cli, subcommand
):
    """The control: `--plan` runs the listing, so the same package resolves."""
    result = invoke("--plan", subcommand, "fake-pkg-alpha")
    stderr = strip_ansi(result.stderr)
    assert result.exit_code == 0
    assert "is not recognized" not in stderr
    assert "Run with --plan" not in stderr


def test_installed_inventory_reads_none_on_a_failing_cli(
    fake_pool, failing_installed_query
):
    """A listing whose CLI raises is no answer, never an empty inventory."""
    assert fake_pool.installed_inventory() is None


def test_installed_inventory_distrusts_an_accumulated_error(fake_pool, monkeypatch):
    """A listing that logged an error instead of raising is no answer either."""

    def noisy_listing(manager):
        manager.cli_errors.append(CLIError(1, "", "Registry unreachable."))
        yield manager.package(id="fake-pkg-alpha", installed_version="1.0.0")

    monkeypatch.setattr(FakeManager, "installed", property(noisy_listing))
    assert fake_pool.installed_inventory() is None


def test_installed_inventory_drops_the_memoized_views(fake_pool):
    """A fresh reading evicts the views memoized before an upgrade."""
    assert fake_pool.installed_ids == frozenset({"fake-pkg-alpha", "fake-pkg-beta"})
    assert "installed_ids" in vars(fake_pool)
    inventory = fake_pool.installed_inventory()
    assert inventory is not None
    assert set(inventory) == {"fake-pkg-alpha", "fake-pkg-beta"}
    assert "installed_ids" not in vars(fake_pool)


def test_upgrade_all_takes_the_listing_it_is_handed(monkeypatch):
    """A full upgrade handed `outdated_ids` never lists the outdated packages."""
    manager = FakeManager()

    def no_native_upgrade(self):
        raise NotImplementedError

    monkeypatch.setattr(FakeManager, "upgrade_all_cli", no_native_upgrade)
    monkeypatch.setattr(
        FakeManager,
        "outdated",
        property(lambda self: pytest.fail("the outdated packages were listed twice")),
    )
    ran = []
    monkeypatch.setattr(manager, "run", lambda *args, **kwargs: ran.append(args[0]))
    manager.upgrade(outdated_ids=("fake-pkg-alpha", "fake-pkg-beta"))
    assert [cli[1:] for cli in ran] == [
        ("upgrade", "fake-pkg-alpha"),
        ("upgrade", "fake-pkg-beta"),
    ]


def _package(package_id, installed_version=None, latest_version=None):
    return Package(
        id=package_id,
        manager_id="orchard",
        installed_version=installed_version,
        latest_version=latest_version,
    )


def test_upgrade_outcomes_classification():
    before = {
        p.id: p
        for p in (
            _package("apple", "1.0"),
            _package("banana", "2.0"),
            _package("cherry", "3.0"),
            _package("fig", "5.0"),
        )
    }
    after = {
        p.id: p
        for p in (
            _package("apple", "1.1"),
            _package("banana", "2.0"),
            _package("cherry", "3.0"),
            _package("kiwi", "0.1"),
        )
    }
    # `grape` is outdated for the manager but in neither reading: no row.
    expected = {
        p.id: p
        for p in (
            _package("banana", "2.0", "2.5"),
            _package("cherry", "3.0", "3.5"),
            _package("grape", "8.0", "9.0"),
        )
    }
    released = datetime(2020, 3, 18, 19, 39, 23, tzinfo=timezone(timedelta(hours=2)))
    held = CooldownHold(released=released, eligible=released + timedelta(days=7))
    rows = package_outcomes(
        before,
        after,
        expected,
        hold=lambda package_id: held if package_id == "banana" else None,
    )
    assert [
        (r["id"], str(r["from_version"] or ""), str(r["to_version"] or ""), r["status"])
        for r in rows
    ] == [
        ("apple", "1.0", "1.1", "upgraded"),
        ("banana", "2.0", "2.5", "held"),
        ("cherry", "3.0", "3.5", "still outdated"),
        ("fig", "5.0", "", "removed"),
        ("kiwi", "", "0.1", "installed"),
    ]
    assert all(isinstance(r["status"], str) for r in rows)
    assert not any(isinstance(r["status"], PackageOutcome) for r in rows)
    # Only the held package is dated, in UTC whatever offset the probe answered in.
    assert {r["id"]: (r["released"], r["eligible"]) for r in rows} == {
        "apple": (None, None),
        "banana": ("2020-03-18T17:39:23+00:00", "2020-03-25T17:39:23+00:00"),
        "cherry": (None, None),
        "fig": (None, None),
        "kiwi": (None, None),
    }


def test_upgrade_outcomes_undated_hold():
    """A release held fail-closed has no date to report."""
    rows = package_outcomes(
        {"plum": _package("plum", "1.0")},
        {"plum": _package("plum", "1.0")},
        {"plum": _package("plum", "1.0", "1.1")},
        hold=lambda _: CooldownHold(),
    )
    assert [(r["status"], r["released"], r["eligible"]) for r in rows] == [
        ("held", None, None)
    ]


@pytest.mark.parametrize(
    ("before", "after", "announced", "status"),
    (
        ("1.0", "1.1", None, "upgraded"),
        ("1.1", "1.0", None, "downgraded"),
        ("2:1.0", "1:2.0", None, "downgraded"),
        # The manager's own listing outranks the version ordering.
        ("2024.10", "1.0", "1.0", "upgraded"),
        ("2024.10", "1.0", None, "downgraded"),
        # A hex hash sorts as a string, in no meaningful order.
        ("f00d1e5", "0badc0de", None, "upgraded"),
        ("1.8.6-125-g6cd4c31", "1.8.6-124-g0badc0d", None, "upgraded"),
        # A version appearing or vanishing has no direction.
        (None, "1.0", None, "upgraded"),
        ("1.0", None, None, "upgraded"),
    ),
)
def test_upgrade_outcomes_direction(before, after, announced, status):
    """A move reads as a downgrade only when its direction is certain."""
    expected = {"plum": _package("plum", before, announced)} if announced else None
    rows = package_outcomes(
        {"plum": _package("plum", before)},
        {"plum": _package("plum", after)},
        expected,
        hold=lambda _: None,
    )
    assert [row["status"] for row in rows] == [status]


def test_upgrade_outcome_glyphs_cover_every_outcome():
    """Every outcome leads its table cell with a glyph of its own."""
    assert set(PACKAGE_OUTCOME_GLYPHS) == set(PackageOutcome)
    assert len(set(PACKAGE_OUTCOME_GLYPHS.values())) == len(PackageOutcome)


def test_upgrade_outcomes_without_an_outdated_listing():
    """A manager that cannot list its outdated packages still reports what moved."""
    before = {"apple": _package("apple", "1.0"), "fig": _package("fig", "5.0")}
    after = {"apple": _package("apple", "1.1"), "fig": _package("fig", "5.0")}
    rows = package_outcomes(before, after, None, hold=lambda _: None)
    assert [(r["id"], r["status"]) for r in rows] == [("apple", "upgraded")]


@pytest.mark.parametrize(
    ("results", "statuses", "detail"),
    (
        (UPGRADE_RESULTS, (), "nothing upgraded"),
        (UPGRADE_RESULTS, ("upgraded",), "1 upgraded"),
        (
            UPGRADE_RESULTS,
            ("upgraded", "upgraded", "installed", "removed"),
            "2 upgraded",
        ),
        (
            UPGRADE_RESULTS,
            ("held", "still outdated", "still outdated"),
            "nothing upgraded, 1 held, 2 still outdated",
        ),
        (UPGRADE_RESULTS, ("upgraded", "held"), "1 upgraded, 1 held"),
        (UPGRADE_RESULTS, ("downgraded",), "nothing upgraded, 1 downgraded"),
        (
            UPGRADE_RESULTS,
            ("upgraded", "downgraded", "held"),
            "1 upgraded, 1 downgraded, 1 held",
        ),
        (SWEEP_RESULTS, (), "nothing removed"),
        (SWEEP_RESULTS, ("removed", "removed", "upgraded"), "2 removed"),
    ),
)
def test_outcome_detail(results, statuses, detail):
    rows = [{"status": status} for status in statuses]
    assert outcome_detail(rows, results) == detail


def test_upgrade_all_reports_what_moved(invoke, changing_fake_pool):
    """The trail line counts the outcomes and the table names each package."""
    result = invoke("upgrade", "--all")
    assert result.exit_code == 0
    mid = changing_fake_pool.id
    stderr = strip_ansi(result.stderr)
    assert f"✓ {mid}.upgrade_all (1 upgraded, 1 downgraded, 1 still outdated)" in stderr
    assert "✓ Upgraded 1/1 managers" in stderr
    check_report(
        result.stdout,
        {
            "fake-pkg-alpha": ("1.0.0", "1.1.0", PackageOutcome.UPGRADED.label),
            "fake-pkg-beta": ("2.5.3", "2.6.0", PackageOutcome.STILL_OUTDATED.label),
            "fake-pkg-epsilon": ("5.2.0", PackageOutcome.REMOVED.label),
            "fake-pkg-gamma": ("0.1.0", PackageOutcome.INSTALLED.label),
            "fake-pkg-zeta": ("3.0.0", "2.9.0", PackageOutcome.DOWNGRADED.label),
        },
    )
    # The package the upgrade never touched earns no row.
    assert "fake-pkg-delta" not in result.stdout
    # No row is dated, so the cooldown columns stay out of the table.
    assert "Released" not in result.stdout
    assert "Eligible" not in result.stdout


def test_upgrade_all_selects_the_cooldown_columns(invoke, changing_fake_pool):
    """`--columns` reaches the cooldown columns of a report carrying no date."""
    result = invoke("upgrade", "--all", "--columns", "package_id,eligible")
    assert result.exit_code == 0
    header = next(line for line in result.stdout.splitlines() if "│" in line)
    assert header.split() == ["│", "Package", "ID", "│", "Eligible", "│"]


def test_upgrade_packages_reports_what_moved(invoke, changing_fake_pool):
    """Upgrading named packages reports each one moved or left behind."""
    result = invoke("upgrade", "fake-pkg-alpha", "fake-pkg-beta")
    assert result.exit_code == 0
    mid = changing_fake_pool.id
    stderr = strip_ansi(result.stderr)
    assert f"✓ {mid}.upgrade: fake-pkg-alpha" in stderr
    assert f"✓ {mid}.upgrade: fake-pkg-beta" in stderr
    check_report(
        result.stdout,
        {
            "fake-pkg-alpha": ("1.0.0", "1.1.0", PackageOutcome.UPGRADED.label),
            # The command succeeded, yet the pinned package did not move.
            "fake-pkg-beta": ("2.5.3", "2.6.0", PackageOutcome.STILL_OUTDATED.label),
            "fake-pkg-gamma": ("0.1.0", PackageOutcome.INSTALLED.label),
        },
    )


def test_upgrade_all_report_serialized(invoke, changing_fake_pool):
    """The serialized report keeps the shape of the other package listings."""
    result = invoke("--table-format", "json", "upgrade", "--all")
    assert result.exit_code == 0
    mid = changing_fake_pool.id
    assert json.loads(result.stdout) == {
        mid: {
            "id": mid,
            "name": changing_fake_pool.name,
            "errors": [],
            "packages": [
                {
                    "id": "fake-pkg-alpha",
                    "name": None,
                    "from_version": "1.0.0",
                    "to_version": "1.1.0",
                    "status": "upgraded",
                    "released": None,
                    "eligible": None,
                },
                {
                    "id": "fake-pkg-beta",
                    "name": None,
                    "from_version": "2.5.3",
                    "to_version": "2.6.0",
                    "status": "still outdated",
                    "released": None,
                    "eligible": None,
                },
                {
                    "id": "fake-pkg-epsilon",
                    "name": None,
                    "from_version": "5.2.0",
                    "to_version": None,
                    "status": "removed",
                    "released": None,
                    "eligible": None,
                },
                {
                    "id": "fake-pkg-gamma",
                    "name": None,
                    "from_version": None,
                    "to_version": "0.1.0",
                    "status": "installed",
                    "released": None,
                    "eligible": None,
                },
                {
                    "id": "fake-pkg-zeta",
                    "name": None,
                    "from_version": "3.0.0",
                    "to_version": "2.9.0",
                    "status": "downgraded",
                    "released": None,
                    "eligible": None,
                },
            ],
        }
    }


@pytest.mark.parametrize("mode", ("--dry-run", "--plan"))
def test_upgrade_all_simulation_skips_the_report(invoke, changing_fake_pool, mode):
    """A simulated upgrade moves nothing, so no diff is taken and none printed."""
    result = invoke(mode, "upgrade", "--all")
    assert result.exit_code == 0
    mid = changing_fake_pool.id
    stderr = strip_ansi(result.stderr)
    assert f"✓ {mid}.upgrade_all (" in stderr
    assert "upgraded" not in stderr
    assert "fake-pkg-" not in result.stdout


class ProbedFakeManager(ChangingFakeManager):
    """Variant the cooldown gates package by package, through the release-date
    probe.

    The latest release of the pinned package is one day old, and every other
    one a month older.
    """

    def __init__(self) -> None:
        super().__init__()
        self.pinned_release = datetime.now(tz=timezone.utc) - timedelta(days=1)
        """When the latest release of the pinned package was published."""

    def release_date(self, package_id):
        if package_id == self.PINNED:
            return self.pinned_release
        return self.pinned_release - timedelta(days=30)


@pytest.fixture
def probed_fake_pool(patch_pool_with):
    """Yield a {class}`ProbedFakeManager`, whose pinned package a week of
    cooldown holds back."""
    return patch_pool_with(ProbedFakeManager())


def test_upgrade_all_dates_a_held_package(invoke, probed_fake_pool):
    """A package the cooldown holds reports when its release was published and
    when it clears the window."""
    result = invoke("--cooldown", "7 days", "upgrade", "--all")
    assert result.exit_code == 0
    mid = probed_fake_pool.id
    stderr = strip_ansi(result.stderr)
    assert f"✓ {mid}.upgrade_all (1 upgraded, 1 downgraded, 1 held)" in stderr
    fresh = probed_fake_pool.pinned_release
    released = fresh.date().isoformat()
    eligible = (fresh + timedelta(days=7)).date().isoformat()
    check_report(
        result.stdout,
        {
            "fake-pkg-alpha": ("1.0.0", "1.1.0", PackageOutcome.UPGRADED.label),
            "fake-pkg-beta": (
                "2.5.3",
                "2.6.0",
                f"{PackageOutcome.HELD.label} │ {released} │ {eligible} │",
            ),
            "fake-pkg-epsilon": ("5.2.0", PackageOutcome.REMOVED.label),
            "fake-pkg-gamma": ("0.1.0", PackageOutcome.INSTALLED.label),
            "fake-pkg-zeta": ("3.0.0", "2.9.0", PackageOutcome.DOWNGRADED.label),
        },
    )
    header = next(line for line in result.stdout.splitlines() if "│" in line)
    assert header.split()[-6:] == ["Status", "│", "Released", "│", "Eligible", "│"]


def test_upgrade_all_dates_a_held_package_serialized(invoke, probed_fake_pool):
    """The serialized report carries both dates as timestamps."""
    result = invoke(
        "--table-format", "json", "--cooldown", "7 days", "upgrade", "--all"
    )
    assert result.exit_code == 0
    fresh = probed_fake_pool.pinned_release
    dates = {
        package["id"]: (package["released"], package["eligible"])
        for package in json.loads(result.stdout)[probed_fake_pool.id]["packages"]
    }
    assert dates == {
        "fake-pkg-alpha": (None, None),
        "fake-pkg-beta": (
            fresh.isoformat(timespec="seconds"),
            (fresh + timedelta(days=7)).isoformat(timespec="seconds"),
        ),
        "fake-pkg-epsilon": (None, None),
        "fake-pkg-gamma": (None, None),
        "fake-pkg-zeta": (None, None),
    }


class ListedFakeManager(ChangingFakeManager):
    """Variant that lists and upgrades its packages the way a real manager does.

    The `installed` listing is what a command printed: the content of
    {attr}`store`, refreshed from the inventory before each call. The command
    line stays the same from one listing to the next, and only its output
    changes.

    Each upgrade command ends on the manager's ID, which the interpreter
    ignores. Two of these managers then tell their commands apart, like `brew`
    and `cask` do with `--formula` and `--cask`: a lane replays the command a
    peer already ran, and a replayed command changes nothing.
    """

    def __init__(self, store):
        super().__init__()
        self.store = store
        """The file the `installed` command prints."""

    @property
    def installed(self):
        self.store.write_text(
            "".join(
                f"{package_id} {version}\n"
                for package_id, version in sorted(self.inventory.items())
            ),
            encoding="UTF-8",
        )
        script = f"print(open({str(self.store)!r}, encoding='UTF-8').read())"
        for line in self.run(str(self.cli_path), "-c", script).splitlines():
            package_id, version = line.split()
            yield self.package(id=package_id, installed_version=version)

    def upgrade_all_cli(self):
        return (*super().upgrade_all_cli(), self.id)

    def upgrade_one_cli(self, package_id, version=None):
        return (*super().upgrade_one_cli(package_id, version), self.id)


class ListedPeerFakeManager(ListedFakeManager):
    """A second manager, for the lock family the first one cannot form alone."""


@pytest.fixture
def lock_family_pool(patch_pool_with, monkeypatch, tmp_path):
    """Yield two managers of one lock family, like `brew` and `cask`.

    Their mutating operations share one lane, and with it the command cache of
    {attr}`~meta_package_manager.execution.CLIExecutor.run_cache`.
    """
    fakes = (
        ListedFakeManager(tmp_path / "first.txt"),
        ListedPeerFakeManager(tmp_path / "peer.txt"),
    )
    family = LockFamily(
        "fake inventory",
        frozenset(fake.id for fake in fakes),
        "they are the two fakes of one test",
    )
    for fake in fakes:
        monkeypatch.setitem(_LOCK_FAMILY_BY_MANAGER, fake.id, family)
    patch_pool_with(*fakes)
    return fakes


@pytest.mark.parametrize(
    ("packages", "statuses"),
    (
        pytest.param(
            ("--all",),
            {
                "fake-pkg-alpha": "upgraded",
                "fake-pkg-beta": "still outdated",
                "fake-pkg-epsilon": "removed",
                "fake-pkg-gamma": "installed",
                "fake-pkg-zeta": "downgraded",
            },
            id="all",
        ),
        pytest.param(
            ("fake-pkg-alpha",),
            {"fake-pkg-alpha": "upgraded", "fake-pkg-gamma": "installed"},
            id="one-package",
        ),
    ),
)
def test_upgrade_reports_each_member_of_a_lock_family(
    invoke, lock_family_pool, packages, statuses
):
    """A lane shared by a lock family never serves a manager the listing it took
    before its upgrade: each member reports what its own upgrade moved."""
    result = invoke("--table-format", "json", "upgrade", *packages)
    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert set(report) == {fake.id for fake in lock_family_pool}
    for fake in lock_family_pool:
        assert {
            package["id"]: package["status"] for package in report[fake.id]["packages"]
        } == statuses, fake.id
