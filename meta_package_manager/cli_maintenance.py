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
"""The maintenance subcommands: the state changers and diagnostics.

`install`, `upgrade`, `remove`, `sync`, `cleanup` and `doctor`, plus
the machinery only they need: the cooldown gate, the sourced-operation
dispatch that resolves each package spec to its source managers, and the
cleanup category selection.

The `mpm` group itself, and the per-package action engine `restore` also
drives, live in {mod}`meta_package_manager.cli`.

```{todo}
Add a `--force`/`--reinstall` flag to `install`.
```
"""

from __future__ import annotations

import logging
import threading
import time

from click_extra import (
    STRING,
    ParameterSource,
    argument,
    columns_option,
    echo,
    option,
    pass_context,
)
from click_extra.theme import get_current_theme as theme

from .capabilities import (
    Operations,
    cleanup_orphan_is_synthesized,
    implements,
    implements_method,
    supports_cleanup_cache,
    supports_cleanup_repair,
)
from .cli import (
    MAINTENANCE,
    ChangeReport,
    exit_on_failures,
    fail_unless_zero_exit,
    install_action,
    mpm,
    outcome_detail,
    package_label,
    package_task,
    run_manager_action,
)
from .cooldown import CooldownPolicy
from .dispatch import (
    OperationTrail,
    collect_from_managers,
    collect_per_package,
    timed_task,
    trail_label,
    warn_jobs_ignored,
)
from .execution import CLIError, elapsed_clock, operation_subject
from .manager import PackageManager
from .pool import pool
from .specifier import Solver, Specifier
from .sudo import diagnose_escalation, inspect_install_root, prime_sudo
from .tables import CHANGE_REPORT_COLUMNS, PackageOutcome, column_specs

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable

    from click_extra import Context


UPGRADE_RESULTS = (
    PackageOutcome.UPGRADED,
    PackageOutcome.DOWNGRADED,
    PackageOutcome.COOLDOWN,
    PackageOutcome.STILL_OUTDATED,
)
"""The outcomes a full upgrade counts on each manager's trail line, the upgrades
first."""

SWEEP_RESULTS = (PackageOutcome.REMOVED,)
"""The outcome an orphan sweep counts on each manager's trail line."""

DRY_RUN_HINT = (
    "--dry-run also simulates the read-only queries, so it cannot find which "
    "manager provides a package. Run with --plan to resolve it."
)
"""Why `--dry-run` leaves a package untied to a manager unresolved, and the option
that resolves it."""


def _simulates_reads(manager: PackageManager) -> bool:
    """Whether `--dry-run` simulates the read-only queries of `manager`.

    `--plan` runs them for real, even when `--dry-run` is also set.
    """
    return manager.dry_run and not manager.plan


def cooldown_permits(manager: PackageManager) -> bool:
    """Decide whether a release-introducing operation may run on `manager`.

    Returns `True` when no cooldown is active, when the manager can enforce it
    (natively, or through the per-package {meth}`release_date
    <meta_package_manager.manager.PackageManager.release_date>` probe), or when
    the manager's resolved {class}`~meta_package_manager.cooldown.CooldownPolicy`
    waives the requirement (`best-effort`) or exempts it outright (`off`).
    Returns `False` (after logging the skip) when an active cooldown cannot be
    enforced and the fail-closed default still holds, so the caller leaves the
    manager alone rather than letting a freshly-published version slip in.

    The skip message names both remedies, the one-shot keyword and the
    persistent configuration key: opting out of a supply-chain safeguard is a
    standing policy decision, not something to re-type on every run.
    """
    if manager.cooldown is None or manager.supports_cooldown:
        return True
    policy = manager.cooldown_policy or CooldownPolicy.enforce
    if policy in (CooldownPolicy.best_effort, CooldownPolicy.off):
        logging.warning(
            "Cannot enforce the release-age cooldown; running without the "
            "supply-chain safeguard.",
            extra={"label": manager.subject},
        )
        return True
    logging.warning(
        "Skipped: cannot enforce the release-age cooldown. Run it anyway with "
        "`--cooldown best-effort`, or set `[mpm.cooldown] policy = "
        '"best-effort"` in your configuration file.',
        extra={"label": manager.subject},
    )
    return False


def _announce_level(ctx: Context) -> int:
    """Log level for a maintenance command's per-manager announcement.

    An explicit `--<id>` selection announces loudly at `INFO`; an implicit
    "run everything" stays at `DEBUG` so the default view shows only the trail
    (matching the explicit/implicit levels `select_managers` already uses for
    its skip messages). Shared by `sync`, `cleanup`, `upgrade --all` and
    `doctor`.

    ```{todo}
    Drop every per-manager announcement (these four, plus `backup`, `restore`
    and `sbom`) once mpm requires a click-extra release labeling the prompt line
    `run_cli` logs. That `info:brew.sync: $ …` line then names the manager, the
    operation and the command, which is all an announcement says. Two things
    move in the same change: the selection tests read an announcement as proof
    a manager acted, and a `restore` section with no package runs no command,
    so the announcement is the only trace it leaves.
    ```
    """
    return logging.INFO if ctx.obj.user_selection else logging.DEBUG


def _maintenance_work(
    announce: int,
    message: str,
    operation: Callable[[PackageManager], object],
) -> Callable[[PackageManager], tuple[str, dict]]:
    """Build a `work` callable for a maintenance command's fan-out.

    Logs `message` at the `announce` level, labeled with the manager's subject
    (rendered into the level prefix, `info:brew.sync:`), runs `operation(manager)`,
    and returns
    ``(id, {"errors": <CLI errors raised during the run>})`` so a manager that grows
    its error list is marked `✘` in the trail. Shared by `sync` and `cleanup`,
    whose work differs only in the message and the manager method.
    """

    def work(manager: PackageManager) -> tuple[str, dict]:
        logging.log(announce, message, extra={"label": manager.subject})
        with manager.new_errors() as errors:
            operation(manager)
        return manager.id, {"errors": errors}

    return work


def _dispatch_sourced_operation(
    ctx: Context,
    packages_specs: tuple[str, ...],
    *,
    operation: Operations,
    action: Callable[[PackageManager, Specifier], str | None],
    verb: str,
    label: str,
    done_label: str,
    apply_cooldown: bool = False,
    report_outdated: bool = False,
) -> None:
    """Resolve each package spec to its source managers, then fan `action` out.

    The shared engine behind `upgrade <packages>` and `remove`. Both resolve every
    spec to the managers that can act on it — the manager named in the spec, or every
    selected manager that reports the package installed — then run `action` per
    (package, manager) concurrently across managers and serially within each (see
    {func}`meta_package_manager.dispatch.collect_per_package`). A package no manager
    recognizes is skipped with an error; any genuine failure exits non-zero with a
    `critical` summary, matching `install`.

    `apply_cooldown` gates each manager through {func}`cooldown_permits` first, so a
    release-introducing `upgrade` skips a manager that cannot honor an active cooldown;
    `remove` (which introduces nothing) leaves it `False`.

    The command closes on the change report of each manager it acted with (see
    {class}`~meta_package_manager.cli.ChangeReport`). `report_outdated` reads the
    outdated listing first, so the report also names each requested package the
    command left behind: `upgrade` sets it.
    """
    selected_managers = tuple(
        ctx.obj.selected_managers(implements_operation=operation),
    )
    manager_ids = tuple(manager.id for manager in selected_managers)

    # Authenticate sudo once up front if any selected manager will escalate, so a
    # password prompt never stalls the concurrent fan-out below. The run reads the
    # inventory to source the specs, and the outdated listing for a report naming
    # what the command left behind.
    reads = [Operations.installed]
    if report_outdated:
        reads.append(Operations.outdated)
    prime_sudo(ctx, selected_managers, operations=(operation, *reads))

    # Subset of selected managers implementing `installed`, queried to discover which
    # manager(s) a spec untied to one was installed with. A manager with no inventory
    # (`sheldon`, `zeroinstall`) still acts on a spec tied to it, so an empty subset
    # is skipped rather than handed to the selection, which exits when nothing is left.
    sourcing_ids = tuple(
        manager.id
        for manager in selected_managers
        if implements(manager, Operations.installed)
    )
    sourcing_managers = (
        tuple(
            ctx.obj.selected_managers(
                keep=sourcing_ids,
                implements_operation=Operations.installed,
            ),
        )
        if sourcing_ids
        else ()
    )

    # Collect every (package, manager) attempt that genuinely failed, to exit non-zero.
    failures: list[str] = []
    # Group every (package, manager) pair by manager: managers run in parallel while each
    # manager's own packages are processed one at a time (see collect_per_package).
    failures_lock = threading.Lock()
    tasks: list[tuple[PackageManager, Callable[[], tuple[bool, str]]]] = []
    # The package IDs each manager acts on, the ones an upgrade expects to move.
    requested: dict[str, set[str]] = {}
    unresolved_in_simulation = False
    solver = Solver(packages_specs, manager_priority=manager_ids)
    for package_id, spec in solver.resolve_package_specs():
        source_manager_ids = set()
        # Use the manager from the spec.
        if spec.manager_id:
            source_manager_ids.add(spec.manager_id)
        # Package is not bound to a manager by the user's specifiers.
        else:
            logging.info(
                f"{spec} not tied to a manager. Search all managers recognizing it.",
            )
            # Find all the managers that have the package installed.
            for manager in sourcing_managers:
                if package_id in manager.installed_ids:
                    logging.info(
                        f"{package_id} has been installed "
                        f"with {theme().invoked_command(manager.id)}.",
                    )
                    source_manager_ids.add(manager.id)
            # A manager keeping no inventory can never be found this way, so when it
            # is the only one selected the package goes to it directly.
            if (
                not source_manager_ids
                and not sourcing_managers
                and len(manager_ids) == 1
            ):
                logging.info(
                    f"{theme().invoked_command(manager_ids[0])} keeps no inventory "
                    f"to look {package_id} up in. Hand it over as is.",
                )
                source_manager_ids.add(manager_ids[0])

        if not source_manager_ids:
            logging.error(
                f"{package_id} is not recognized by any of the selected managers. "
                "Skip it.",
            )
            if any(_simulates_reads(manager) for manager in sourcing_managers):
                unresolved_in_simulation = True
            continue

        # Announce the managers we will act with (also the non-TTY signal).
        logging.info(
            f"{verb.capitalize()} {package_id} "
            f"with {', '.join(map(theme().invoked_command, sorted(source_manager_ids)))}",
        )
        # One task per (package, manager); a package acted on by two managers tallies as
        # two. For upgrade, skip a manager that cannot honor an active cooldown.
        for manager_id in sorted(source_manager_ids):
            manager = pool.get(manager_id)
            if apply_cooldown and not cooldown_permits(manager):
                continue
            requested.setdefault(manager.id, set()).add(package_id)
            tasks.append((
                manager,
                package_task(
                    manager,
                    spec,
                    failures_lock,
                    action=action,
                    verb=verb,
                    # Each task re-stamps the mutating operation for its own
                    # attempt: the sourcing selection above stamped `installed` on
                    # the shared manager singletons, and the timeout and stall
                    # watchdog are keyed on the active operation.
                    operation=operation.name,
                    record_failure=lambda s: failures.append(package_label(s)),
                ),
            ))

    report = ChangeReport()
    collect_per_package(
        label,
        done_label,
        report.bracket(tasks, outdated=requested if report_outdated else None),
        operation=operation.name,
    )
    report.show(ctx)
    if unresolved_in_simulation:
        logging.warning(DRY_RUN_HINT)

    exit_on_failures(ctx, verb, failures)


def _attempt_install(manager: PackageManager, spec: Specifier) -> str:
    """Try installing one `spec` with one `manager`, returning the trail status.

    Thin adapter of {func}`run_manager_action` for the sequential install
    paths, whose callers map the returned status (`installed`, `failed` or
    `cooldown`) onto their `✓`/`✘` ledger and decide the retry/stop semantics
    (the tied loop records every miss; the untied priority search falls
    through to the next manager). The `cooldown` status reports a package held
    back by the per-package release-age probe: `✘` on the trail, but never a
    recorded failure, so it cannot force a non-zero exit on its own.
    """
    hold = manager.cooldown_hold(spec.package_id)
    if hold:
        logging.warning(
            f"Hold {package_label(spec)}: {hold.reason}.",
            extra={"label": manager.subject},
        )
        return "cooldown"
    installed = run_manager_action(
        manager,
        spec,
        action=install_action,
        verb="install",
        operation=Operations.install.name,
    )
    return "installed" if installed else "failed"


def _cooldown_skip_task(
    manager_id: str, spec: Specifier
) -> Callable[[], tuple[bool, str]]:
    """Build the task marking a tied package `✘` on a manager the cooldown skips.

    {func}`cooldown_permits` already logged why. The skip is `✘` on the trail
    but never a recorded failure, so it cannot force a non-zero exit on its own.
    """

    def task() -> tuple[bool, str]:
        subject = operation_subject(manager_id, Operations.install.name)
        return False, trail_label(subject, package_label(spec), "cooldown")

    return task


def _tied_install_tasks(
    packages_per_managers: dict[str | None, set[Specifier]],
    failures_lock: threading.Lock,
    unresolved_labels: list[str],
) -> list[tuple[PackageManager, Callable[[], tuple[bool, str]]]]:
    """Build one install task per package the solver tied to a manager.

    A tied package has exactly one candidate manager, so a miss is final: the
    task records it in `unresolved_labels` (forcing a non-zero exit) and marks
    the `✘` trail. A package held by the cooldown is `✘` too, but never
    unresolved. A manager that cannot honor an active cooldown gets its tied
    packages dropped once, through {func}`_cooldown_skip_task`.
    """
    tasks: list[tuple[PackageManager, Callable[[], tuple[bool, str]]]] = []
    for manager_id, package_specs in packages_per_managers.items():
        if not manager_id:
            continue
        manager = pool.get(manager_id)
        permitted = cooldown_permits(manager)
        for spec in package_specs:
            if permitted:
                task = package_task(
                    manager,
                    spec,
                    failures_lock,
                    action=install_action,
                    verb="install",
                    operation=Operations.install.name,
                    record_failure=lambda s: unresolved_labels.append(package_label(s)),
                )
            else:
                task = _cooldown_skip_task(manager_id, spec)
            tasks.append((manager, task))
    return tasks


@mpm.command(
    short_help="Install a package.",
    section=MAINTENANCE,
    examples=[
        ("Install with the first manager carrying the package", "mpm install jq"),
        ("Install with one manager only", "mpm --brew install jq"),
        ("Pin the version to install", "mpm install jq@1.7.1"),
        ("Name the manager in the specifier itself", "mpm install pkg:npm/left-pad"),
    ],
)
@argument(
    "packages_specs",
    type=STRING,
    nargs=-1,
    required=True,
    help="A mix of plain <package_id>, simple <package_id@version> specifiers or full "
    "<pkg:npm/left-pad> purls.",
)
@columns_option(columns=column_specs(CHANGE_REPORT_COLUMNS))
@pass_context
def install(ctx, packages_specs):
    """Install one or more packages.

    This subcommand is sensible to the order of the package managers selected by the
    user.

    Installation will first proceed for all the packages found to be tied to a specific
    manager. Which is the case for packages provided with precise package specifiers
    (like purl). This will also happens in situations in which a tighter selection of
    managers is provided by the user.

    For packages whose manager is not known, or if multiple managers are candidates for
    the installation, mpm will try to find the best manager to install it with.

    Installation will be attempted with each manager, in the order they were selected.
    If a search for the package ID returns no result from the highest-priority manager,
    we will skip the installation and try the next available managers in the order of
    their priority.
    """
    # Cast generator to tuple because of reuse.
    selected_managers = tuple(
        ctx.obj.selected_managers(implements_operation=Operations.install),
    )
    manager_ids = tuple(manager.id for manager in selected_managers)
    logging.info(
        "Installation priority: > "
        f"{' > '.join(map(theme().invoked_command, manager_ids))}",
    )

    # Authenticate sudo once up front if any selected manager will escalate, covering
    # both the concurrent tied-package fan-out and the sequential priority search below.
    # The run also reads the inventory, for its report and to mark a dependency as
    # explicit.
    prime_sudo(
        ctx,
        selected_managers,
        operations=(Operations.install, Operations.installed, Operations.search),
    )

    solver = Solver(packages_specs, manager_priority=manager_ids)
    packages_per_managers = solver.resolve_specs_group_by_managers()
    unmatched_packages = packages_per_managers.get(None, set())

    # Collect the label of every requested spec that no manager could install, to
    # raise a non-zero exit code at the end of the command.
    unresolved_labels: list[str] = []
    failures_lock = threading.Lock()
    tasks = _tied_install_tasks(packages_per_managers, failures_lock, unresolved_labels)
    # Frames each manager's installs with two inventory readings (see ChangeReport).
    report = ChangeReport()

    # Packages tied to a manager (purls, or a single-manager selection) install
    # concurrently across managers, serial within each (see collect_per_package). An
    # untied package needs a priority search (install with the first manager that has
    # it, skip the rest), which is cross-manager-sequential; its presence drops the
    # whole command onto the sequential path below.
    if not unmatched_packages:
        collect_per_package(
            "Installing",
            "Installed",
            report.bracket(tasks),
            operation=Operations.install.name,
        )
        report.show(ctx)
        exit_on_failures(ctx, "install", unresolved_labels)
        return

    # Untied packages present: the priority search cannot fan out, so run sequentially
    # (see warn_jobs_ignored).
    warn_jobs_ignored(ctx)

    # Leave a per-package ✓/✘ ledger plus a persistent finisher (see OperationTrail),
    # keyed by package and its resolving manager.
    total = sum(len(specs) for specs in packages_per_managers.values())
    op = OperationTrail(selected_managers)
    installed_count = 0

    # Install all packages deterministically tied to a specific manager, through the
    # very tasks the concurrent path runs, one at a time. Each manager opens on its
    # first attempt, here or in the priority search below, and all close at the end.
    for manager, task in tasks:
        report.open(manager)
        ok, text = timed_task(task)
        installed_count += ok
        op.mark(ok, text)

    def trail(spec: Specifier, manager_id: str, status: str, seconds: float) -> None:
        """Map an install attempt to a `✓`/`✘` ledger line through `op`.

        `status` is `installed` (✓), or `not_found` / `simulated` / `failed` /
        `cooldown` (✘). `seconds` is how long the attempt took, closing the line
        the way every other trail line closes.
        """
        detail = {
            "not_found": "not found",
            "simulated": "dry-run",
            "cooldown": "cooldown",
        }.get(status)
        subject = operation_subject(manager_id, Operations.install.name)
        text = trail_label(subject, package_label(spec), detail)
        op.mark(status == "installed", f"{text}{elapsed_clock(seconds)}")

    # Drop managers that cannot honor an active cooldown (once, not per package).
    eligible_managers = tuple(m for m in selected_managers if cooldown_permits(m))
    simulated_search = False
    for spec in unmatched_packages:
        installed = False
        held = False
        for manager in eligible_managers:
            start = time.monotonic()
            # Is the package available on this manager? The per-attempt reason is INFO
            # narration; the ✘ trail line below names the manager that missed.
            matches = None
            try:
                # refiltered_search runs the read-only `search` operation. Stamp it
                # as such for the duration of the query so it resolves the read-only
                # timeout and does not arm the mutating stall watchdog: an internal
                # escalator (cask) would otherwise misread a slow search as a hidden
                # password prompt.
                with manager.acting_as(Operations.search.name):
                    matches = tuple(
                        manager.refiltered_search(
                            extended=False,
                            exact=True,
                            query=spec.package_id,
                        ),
                    )
            except NotImplementedError:
                logging.info(
                    "Does not implement search operation.",
                    extra={"label": manager.subject},
                )
                logging.info(
                    f"{spec.package_id} existence unconfirmed, "
                    "try to directly install it...",
                )
            except CLIError:
                logging.info(
                    f"Could not search for {spec.package_id}.",
                    extra={"label": manager.subject},
                )
                trail(spec, manager.id, "not_found", time.monotonic() - start)
                continue
            else:
                if not matches and _simulates_reads(manager):
                    logging.info(
                        f"Search for {spec.package_id} only simulated.",
                        extra={"label": manager.subject},
                    )
                    trail(spec, manager.id, "simulated", time.monotonic() - start)
                    simulated_search = True
                    continue
                if not matches:
                    logging.info(
                        f"No {spec.package_id} package found.",
                        extra={"label": manager.subject},
                    )
                    trail(spec, manager.id, "not_found", time.monotonic() - start)
                    continue
                # Prevents any incomplete or bad implementation of exact search.
                if len(matches) != 1:
                    msg = "Exact search returned multiple packages."
                    raise ValueError(msg)

            report.open(manager)
            status = _attempt_install(manager, spec)
            # A package held by the cooldown ends the search: the highest-
            # priority manager providing it has answered, and falling through
            # to another ecosystem would sidestep the safeguard.
            if status == "cooldown":
                held = True
                trail(spec, manager.id, "cooldown", time.monotonic() - start)
                break
            # On a failed install, fall through to the next manager in priority order.
            if status == "failed":
                trail(spec, manager.id, "failed", time.monotonic() - start)
                continue
            # Stop at the first (highest-priority) manager that provides the package.
            installed = True
            installed_count += 1
            trail(spec, manager.id, "installed", time.monotonic() - start)
            break

        if not installed and not held:
            unresolved_labels.append(package_label(spec))

    op.finish(installed_count == total, f"Installed {installed_count}/{total} packages")
    report.close_all()
    report.show(ctx)
    if simulated_search:
        logging.warning(DRY_RUN_HINT)

    # Fail with a non-zero exit code if any requested package went uninstalled by every
    # selected manager.
    exit_on_failures(ctx, "install", unresolved_labels)


@mpm.command(
    aliases=["update"],
    short_help="Upgrade packages.",
    section=MAINTENANCE,
    examples=[
        ("Upgrade every outdated package of every manager", "mpm upgrade --all"),
        ("Upgrade two packages wherever they are installed", "mpm upgrade curl jq"),
        (
            "Sit out the first days of each new release",
            'mpm --cooldown "7 days" upgrade --all',
        ),
    ],
)
@option(
    "-A",
    "--all",
    is_flag=True,
    default=False,
    help="Upgrade all outdated packages. "
    "Will make the command ignore package IDs provided as parameters.",
)
@columns_option(columns=column_specs(CHANGE_REPORT_COLUMNS))
@argument(
    "packages_specs",
    type=STRING,
    nargs=-1,
    help="A mix of plain <package_id>, simple <package_id@version> specifiers or full "
    "<pkg:npm/left-pad> purls.",
)
@pass_context
def upgrade(ctx, all, packages_specs):
    """Upgrade one or more outdated packages.

    All outdated package will be upgraded by default if no specifiers are provided as
    arguments. I.e. assumes -A/--all option if no [PACKAGES_SPECS]....

    Packages recognized by multiple managers will be upgraded with each of them. You can
    fine-tune this behavior with more precise package specifiers (like purl) and/or
    tighter selection of managers.

    Packages unrecognized by any selected manager will be skipped.
    """
    if not all and not packages_specs:
        logging.info("No package provided, assume -A/--all option.")
        all = True

    # Full upgrade: one ✓/✘ ledger line per manager plus a finisher (see
    # OperationTrail). A manager fails its line if it grows cli_errors while running.
    if all:
        if packages_specs:
            # Deduplicate and sort specifiers for terseness.
            logging.info(
                f"Ignore {', '.join(sorted(set(packages_specs)))} specifiers "
                "and proceed to a full upgrade...",
            )
        managers = list(
            ctx.obj.selected_managers(implements_operation=Operations.upgrade_all),
        )
        # A full upgrade can fall back to upgrading the packages one by one, and
        # reads the inventory and the outdated listing for its report.
        prime_sudo(
            ctx,
            managers,
            operations=(
                Operations.upgrade_all,
                Operations.upgrade,
                Operations.installed,
                Operations.outdated,
            ),
        )
        announce = _announce_level(ctx)
        report = ChangeReport(managers)

        def upgrade_all_work(manager: PackageManager) -> tuple[str, dict]:
            # cooldown_permits() already logs the reason at WARNING when it blocks;
            # mark the manager ✘ without running its CLI.
            if not cooldown_permits(manager):
                return manager.id, {
                    "failed": True,
                    "detail": "cooldown",
                }
            logging.log(
                announce,
                "Upgrade all outdated packages.",
                extra={"label": manager.subject},
            )
            # Two inventory readings frame the native upgrade (see ChangeReport).
            # The outdated listing rides along to name what did not move, and is
            # handed to the upgrade so the paths enumerating it do not list twice.
            expected = report.open(manager, outdated=True)
            with manager.new_errors() as errors:
                output = manager.upgrade(
                    outdated_ids=None if expected is None else tuple(expected),
                )
            if output:
                logging.info(output, extra={"label": manager.subject})
            data: dict = {"errors": errors}
            rows = report.close(manager)
            if rows is not None:
                data["detail"] = outcome_detail(rows, UPGRADE_RESULTS)
            return manager.id, data

        # Full upgrade is independent per manager, so fan out concurrently with a
        # ✓/✘ trail and a success-count finisher (see collect_from_managers).
        collect_from_managers(
            "Upgrading",
            "Upgraded",
            managers,
            upgrade_all_work,
            report_state=True,
            operation=Operations.upgrade_all.name,
        )
        report.show(ctx)
        ctx.exit()

    _dispatch_sourced_operation(
        ctx,
        packages_specs,
        operation=Operations.upgrade,
        action=lambda m, s: m.upgrade(s.package_id, version=s.version),
        verb="upgrade",
        label="Upgrading",
        done_label="Upgraded",
        apply_cooldown=True,
        report_outdated=True,
    )


@mpm.command(
    aliases=["uninstall"],
    short_help="Remove a package.",
    section=MAINTENANCE,
    examples=[
        ("Remove a package from every manager carrying it", "mpm remove jq"),
        ("Remove it and the dependencies it pulled in", "mpm remove --orphans jq"),
    ],
)
@option(
    "--orphans",
    is_flag=True,
    default=False,
    help="Also remove the dependencies the package pulled in that no other package "
    "needs, using each manager's native cascade verb. Managers without one remove the "
    "package only.",
)
@argument(
    "packages_specs",
    type=STRING,
    nargs=-1,
    required=True,
    help="A mix of plain <package_id>, simple <package_id@version> specifiers or full "
    "<pkg:npm/left-pad> purls.",
)
@columns_option(columns=column_specs(CHANGE_REPORT_COLUMNS))
@pass_context
def remove(ctx, orphans, packages_specs):
    """Remove one or more packages.

    Packages recognized by multiple managers will be remove with each of them. You can
    fine-tune this behavior with more precise package specifiers (like purl) and/or
    tighter selection of managers.

    Packages unrecognized by any selected manager will be skipped. A manager keeping
    no inventory, like sheldon, recognizes none, so when it is the only one selected
    it is handed every package as is.

    With `--orphans`, each package is removed together with the dependencies it alone
    pulled in, mapped to the manager's native cascade verb (``apt remove
    --auto-remove`, `pacman --remove --recursive`, `dnf autoremove``, ...). Managers
    with no such verb remove the package only.
    """

    def remove_action(manager: PackageManager, spec: Specifier) -> str | None:
        # --orphans routes to the native cascade verb, falling back to the plain
        # removal (with an INFO capability-skip) for managers that lack one. The
        # NotImplementedError is caught here so it never reaches package_task, which
        # would otherwise record the package as a failure.
        if orphans:
            try:
                return manager.remove_orphan(spec.package_id)
            except NotImplementedError:
                logging.info(
                    "Does not implement orphan removal, removing the package only.",
                    extra={"label": manager.subject},
                )
        return manager.remove(spec.package_id)

    _dispatch_sourced_operation(
        ctx,
        packages_specs,
        operation=Operations.remove,
        action=remove_action,
        verb="remove",
        label="Removing",
        done_label="Removed",
    )


@mpm.command(
    short_help="Sync local package info.",
    section=MAINTENANCE,
    examples=[
        ("Refresh the package metadata of every manager", "mpm sync"),
        ("Refresh one manager only", "mpm --apt sync"),
    ],
)
@pass_context
def sync(ctx):
    """Sync local package metadata and info from external sources."""
    managers = list(ctx.obj.selected_managers(implements_operation=Operations.sync))
    prime_sudo(ctx, managers, operations=(Operations.sync,))
    announce = _announce_level(ctx)

    # Sync is independent per manager, so fan out concurrently with a ✓/✘ trail and
    # a success-count finisher (see collect_from_managers).
    collect_from_managers(
        "Syncing",
        "Synced",
        managers,
        _maintenance_work(announce, "Sync package info.", lambda m: m.sync()),
        report_state=True,
    )


CLEANUP_CATEGORIES = ("orphans", "cache", "repair")
"""Cumulative categories the `cleanup` subcommand decomposes into.

Each category has a two-sided `--<category>/--skip-<category>` flag pair.
Positive flags narrow the run to exactly the listed categories; skip flags
subtract categories from the default selection.
"""


DEFAULT_CLEANUP_CATEGORIES = frozenset({"cache", "repair"})
"""Categories a plain `cleanup` (no category flag) runs.

The orphan sweep is deliberately absent: it removes packages, where cache
pruning and state repair only reclaim disk and fix metadata. Keeping it
strictly behind an explicit `--orphans` makes the default non-destructive
and identical on every manager, native sweep or not, mirroring how `remove`
keeps its cascade behind the same flag.
"""


def _cleanup_steps(
    manager: PackageManager,
    selected: frozenset[str],
    explicit_orphans: bool,
) -> list[tuple[str, Callable[[], None]]]:
    """The `(category, step)` pairs `manager` runs for the `selected` categories.

    A manager runs exactly the category methods it natively overrides, in category
    order. The synthesized orphan sweep engages only on an explicit positive
    `--orphans` (`explicit_orphans`): a skip flag subtracts from the native
    categories and must never make a manager remove packages its plain `cleanup`
    would have left alone. The category names feed the per-manager narration and
    the `✓`/`✘` trail labels, so the run discloses which categories each
    manager was dispatched.
    """
    steps: list[tuple[str, Callable[[], None]]] = []
    if "orphans" in selected and (
        implements_method(manager, "cleanup_orphan")
        or (explicit_orphans and cleanup_orphan_is_synthesized(manager))
    ):
        steps.append(("orphans", manager.cleanup_orphan))
    if "cache" in selected and supports_cleanup_cache(manager):
        steps.append(("cache", manager.cleanup_cache))
    if "repair" in selected and supports_cleanup_repair(manager):
        steps.append(("repair", manager.cleanup_repair))
    return steps


@mpm.command(
    short_help="Cleanup local data.",
    section=MAINTENANCE,
    examples=[
        ("Prune caches and repair local state", "mpm cleanup"),
        ("Also remove the packages nothing requires", "mpm cleanup --orphans"),
        ("Prune caches and nothing else", "mpm cleanup --skip-repair"),
    ],
)
@option(
    "--orphans/--skip-orphans",
    "orphans",
    default=False,
    help="Remove orphaned packages (those nothing depends on anymore) using each "
    "manager's system-wide sweep, native or synthesized from its orphan listing. "
    "The only category removing packages, so it never runs unless requested.",
)
@option(
    "--cache/--skip-cache",
    "cache",
    default=True,
    help="Prune caches, downloads and other left-over artifacts. The broadest "
    "category: for most managers the whole cleanup amounts to it.",
)
@option(
    "--repair/--skip-repair",
    "repair",
    default=True,
    help="Verify and repair the manager's local installation state (like "
    "`flatpak repair`).",
)
@columns_option(columns=column_specs(CHANGE_REPORT_COLUMNS))
@pass_context
def cleanup(ctx, orphans, cache, repair):
    """Cleanup local data and temporary artifacts.

    The work decomposes into cumulative categories, each with a two-sided flag pair:
    `--orphans/--skip-orphans` (system-wide orphan sweep), `--cache/--skip-cache`
    (caches, downloads and left-overs) and `--repair/--skip-repair` (local state
    verification). Positive flags narrow the run to exactly the listed categories;
    skip flags subtract from the default selection.

    A plain `cleanup` runs the cache and repair categories and never removes a
    package: the orphan sweep is the one destructive category, so it only runs on an
    explicit `--orphans`, uniformly across managers, just as `remove` keeps its
    dependency cascade behind the same flag. A manager with no native sweep verb but
    a native orphan listing gets the sweep synthesized: list the orphans, remove them
    one by one, and repeat until none are left. Managers supporting none of the
    selected categories are skipped.
    """
    flags = {"orphans": orphans, "cache": cache, "repair": repair}
    # The cache and repair pairs default to True so --help renders their default as
    # the positive flag name ([default: cache]), while the destructive orphans pair
    # defaults to False and renders [default: skip-orphans]. Whether the user
    # actually touched a flag is recovered from its parameter source: an untouched
    # pair follows the collective selection rule instead of counting as a positive
    # or a skip. A value from the command line, an environment variable or a
    # configuration file all count as explicit. Each two-sided pair resolves to one
    # value (the last flag wins in click), so positives and skips are disjoint by
    # construction.
    explicit = {
        category
        for category in flags
        if ctx.get_parameter_source(category) is not ParameterSource.DEFAULT
    }
    positives = {
        category for category, value in flags.items() if value and category in explicit
    }
    skips = {
        category
        for category, value in flags.items()
        if not value and category in explicit
    }
    if positives:
        selected = frozenset(positives)
    else:
        selected = DEFAULT_CLEANUP_CATEGORIES - skips
        if not selected:
            ctx.fail("Every cleanup category is skipped.")

    managers = list(ctx.obj.selected_managers(implements_operation=Operations.cleanup))

    explicit_orphans = "orphans" in positives
    # Keep only the managers with at least one step to run for the selection: a
    # manager implementing solely the orphan category (cave, pkg-tools) is thus
    # skipped by the non-destructive default and reached through --orphans.
    managers = [m for m in managers if _cleanup_steps(m, selected, explicit_orphans)]

    # The orphan sweep lists the orphans, removes them, and reads the inventory for
    # its report.
    sweep = (Operations.orphans, Operations.remove, Operations.installed)
    prime_sudo(
        ctx,
        managers,
        operations=(Operations.cleanup, *(sweep if "orphans" in selected else ())),
    )
    announce = _announce_level(ctx)
    report = ChangeReport(managers)

    def cleanup_work(manager: PackageManager) -> tuple[str, dict]:
        # A bespoke variant of _maintenance_work: managers run different category
        # subsets, so both the narration and the trail label disclose each
        # manager's own dispatch (`✓ brew.cleanup (cache)`).
        steps = _cleanup_steps(manager, selected, explicit_orphans)
        categories = [category for category, _step in steps]
        logging.log(
            announce,
            f"Clean up {', '.join(categories)}.",
            extra={"label": manager.subject},
        )
        # The orphan sweep is the one category removing packages, so two
        # inventory readings frame the run to report what it removed (see
        # ChangeReport). Its count joins the category on the trail line.
        sweeps = "orphans" in categories
        if sweeps:
            report.open(manager)
        with manager.new_errors() as errors:
            for _category, step in steps:
                step()
        if sweeps:
            rows = report.close(manager)
            if rows is not None:
                categories[categories.index("orphans")] = (
                    f"orphans: {outcome_detail(rows, SWEEP_RESULTS)}"
                )
        return manager.id, {"errors": errors, "detail": ", ".join(categories)}

    # Cleanup is independent per manager, so fan out concurrently with a ✓/✘ trail
    # and a success-count finisher (see collect_from_managers).
    collect_from_managers(
        "Cleaning up",
        "Cleaned",
        managers,
        cleanup_work,
        report_state=True,
    )
    report.show(ctx)


@mpm.command(
    aliases=["check", "diagnose"],
    short_help="Diagnose managers health.",
    section=MAINTENANCE,
    examples=[
        ("Relay the self-diagnosis of every manager", "mpm doctor"),
        ("Diagnose one manager", "mpm --brew doctor"),
    ],
)
@pass_context
def doctor(ctx):
    """Run each manager's native self-diagnosis and relay its report.

    Read-only: nothing is modified. Each manager runs its own diagnostic verb
    (`brew doctor`, `pip check`, `pacman --database --check`, `npm doctor`,
    ...), its health is read from that command's exit code, and its report — the
    diagnosis being the product, not something `mpm` can parse — is relayed
    verbatim to `<stdout>`, one section per manager with findings.

    The trail marks each manager `✓` (healthy) or `✘` (problems found), and the
    run exits non-zero when any manager reports problems, so the command can gate a
    CI job. `-0`/`--zero-exit` keeps the exit code at `0`. Managers with no
    diagnostic verb are skipped. When none of the selected managers has one, the
    escalation report below is the whole diagnosis, and the run exits `0`.

    A first section reports how privilege escalation stands: the escalator mpm
    drives, whether its credentials are ready, whether a password prompt would
    hold for the whole run, and the fix when they are not. It never prompts, and
    never changes the exit code.
    """
    # Escalation belongs to the host, so every selected manager counts, not only
    # those with a diagnostic verb. Probed before priming, which could warm the
    # credentials it reports on.
    selected = list(ctx.obj.selected_managers(allow_empty=True))
    escalation = diagnose_escalation(selected).lines()
    echo("Privilege escalation:")
    for line in escalation:
        echo(line)
    echo()
    # An empty selection stays the usual error, after the report. Selected
    # managers that all lack a diagnostic verb are not one: the report above
    # is then the whole diagnosis.
    managers = list(
        ctx.obj.selected_managers(
            implements_operation=Operations.doctor,
            allow_empty=bool(selected),
        ),
    )
    if not managers:
        logging.warning("None of the selected managers has a diagnostic verb.")
        return
    prime_sudo(ctx, managers, operations=(Operations.doctor,))
    announce = _announce_level(ctx)

    def doctor_work(manager: PackageManager) -> tuple[str, dict]:
        logging.log(announce, "Check health.", extra={"label": manager.subject})
        healthy, report = manager.doctor()
        # Resolved here so the probes overlap with the diagnoses in the same
        # concurrent fan-out. Informational only: ownership never flips health.
        return manager.id, {
            "failed": not healthy,
            "report": report,
            "root": inspect_install_root(manager),
        }

    # The diagnosis is independent per manager, so fan out concurrently with a
    # ✓/✘ trail and a success-count finisher; reports are relayed afterwards, in
    # manager order, so concurrent runs never interleave their output.
    results = collect_from_managers(
        "Diagnosing", "Diagnosed", managers, doctor_work, report_state=True
    )

    unhealthy = []
    for manager_id, data in results:
        # A skipped manager leaves its input-order slot empty.
        if not manager_id:
            continue
        if data.get("failed"):
            unhealthy.append(manager_id)
        report = (data.get("report") or "").strip()
        root = data.get("root")
        if report or root:
            echo(f"{theme().invoked_command(manager_id)}:")
            if root:
                echo(f"Install root: {root.path} (owned by {root.owner_name})")
            if report:
                echo(report)
            echo()

    if unhealthy:
        plural = "s" if len(unhealthy) > 1 else ""
        fail_unless_zero_exit(
            ctx,
            f"{len(unhealthy)} manager{plural} reported problems "
            f"({', '.join(sorted(unhealthy))}).",
        )
