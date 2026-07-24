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
"""

from __future__ import annotations

import logging
import threading

from click_extra import STRING, ParameterSource, argument, echo, option, pass_context
from click_extra.theme import get_current_theme as theme

from .capabilities import (
    Operations,
    cleanup_orphan_is_synthesized,
    implements_method,
    supports_cleanup_cache,
    supports_cleanup_repair,
)
from .cli import (
    MAINTENANCE,
    _install_action,
    _package_task,
    _run_manager_action,
    exit_on_failures,
    fail_unless_zero_exit,
    mpm,
    package_label,
)
from .dispatch import (
    OperationTrail,
    collect_from_managers,
    collect_per_package,
    warn_jobs_ignored,
)
from .execution import CLIError
from .manager import PackageManager
from .pool import pool
from .specifier import Solver, Specifier
from .sudo import prime_sudo

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable

    from click_extra import Context


def cooldown_permits(manager: PackageManager) -> bool:
    """Decide whether a release-introducing operation may run on `manager`.

    Returns `True` when no cooldown is active, when the manager can enforce it
    natively, or when the user opted out of the requirement with
    `--allow-unsupported-managers`. Returns `False` (after logging the skip)
    when an active cooldown cannot be enforced and the requirement still holds, so
    the caller leaves the manager alone rather than letting a freshly-published
    version slip in.
    """
    if manager.cooldown is None or manager.supports_cooldown:
        return True
    if not manager.require_cooldown_support:
        logging.warning(
            "Cannot enforce the release-age cooldown; running without the "
            "supply-chain safeguard.",
            extra={"label": manager.id},
        )
        return True
    logging.warning(
        "Skipped: cannot enforce the release-age cooldown. "
        "Use --allow-unsupported-managers to run it anyway.",
        extra={"label": manager.id},
    )
    return False


def _announce_level(ctx: Context) -> int:
    """Log level for a maintenance command's per-manager announcement.

    An explicit `--<id>` selection announces loudly at `INFO`; an implicit
    "run everything" stays at `DEBUG` so the default view shows only the trail
    (matching the explicit/implicit levels `select_managers` already uses for
    its skip messages). Shared by `sync`, `cleanup` and `upgrade --all`.
    """
    return logging.INFO if ctx.obj.user_selection else logging.DEBUG


def _maintenance_work(
    announce: int,
    message: str,
    operation: Callable[[PackageManager], object],
) -> Callable[[PackageManager], tuple[str, dict]]:
    """Build a `work` callable for a maintenance command's fan-out.

    Logs `message` at the `announce` level, tagged with the manager ID (rendered
    into the level prefix, `info:brew:`), runs `operation(manager)`, and returns
    ``(id, {"errors": <CLI errors raised during the run>})`` so a manager that grows
    its error list is marked `✗` in the trail. Shared by `sync` and `cleanup`,
    whose work differs only in the message and the manager method.
    """

    def work(manager: PackageManager) -> tuple[str, dict]:
        logging.log(announce, message, extra={"label": manager.id})
        before = len(manager.cli_errors)
        operation(manager)
        return manager.id, {"errors": manager.cli_errors[before:]}

    return work


def _dispatch_sourced_operation(
    ctx: Context,
    packages_specs: tuple[str, ...],
    *,
    operation: Operations,
    action: Callable[[PackageManager, Specifier], str | None],
    verb: str,
    past: str,
    prep: str,
    label: str,
    done_label: str,
    apply_cooldown: bool = False,
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
    """
    selected_managers = tuple(
        ctx.obj.selected_managers(implements_operation=operation),
    )
    manager_ids = tuple(manager.id for manager in selected_managers)

    # Authenticate sudo once up front if any selected manager will escalate, so a
    # password prompt never stalls the concurrent fan-out below.
    prime_sudo(ctx, selected_managers)

    # Subset of selected managers implementing `installed`, queried to discover which
    # manager(s) a spec untied to one was installed with.
    sourcing_managers = tuple(
        ctx.obj.selected_managers(
            keep=manager_ids,
            implements_operation=Operations.installed,
        ),
    )

    # Collect every (package, manager) attempt that genuinely failed, to exit non-zero.
    failures: list[str] = []
    # Group every (package, manager) pair by manager: managers run in parallel while each
    # manager's own packages are processed one at a time (see collect_per_package).
    failures_lock = threading.Lock()
    tasks: list[tuple[PackageManager, Callable[[], tuple[bool, str]]]] = []
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

        if not source_manager_ids:
            logging.error(
                f"{package_id} is not recognized by any of the selected manager. "
                "Skip it.",
            )
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
            tasks.append((
                manager,
                _package_task(
                    manager,
                    spec,
                    failures_lock,
                    action=action,
                    verb=verb,
                    past=past,
                    prep=prep,
                    # Each task re-stamps the mutating operation for its own
                    # attempt: the sourcing selection above stamped `installed` on
                    # the shared manager singletons, and the timeout and stall
                    # watchdog are keyed on the active operation.
                    operation=operation.name,
                    record_failure=lambda s: failures.append(package_label(s)),
                ),
            ))

    collect_per_package(label, done_label, tasks)

    exit_on_failures(ctx, verb, failures)


def _attempt_install(manager: PackageManager, spec: Specifier) -> bool:
    """Try installing one `spec` with one `manager`, returning success.

    Thin adapter of {func}`_run_manager_action` for the sequential install
    paths, whose callers map the result onto their `✓`/`✗` ledger and decide
    the retry/stop semantics (the tied loop records every miss; the untied
    priority search falls through to the next manager).
    """
    return _run_manager_action(
        manager,
        spec,
        action=_install_action,
        verb="install",
        operation=Operations.install.name,
    )


@mpm.command(short_help="Install a package.", section=MAINTENANCE)
@argument(
    "packages_specs",
    type=STRING,
    nargs=-1,
    required=True,
    help="A mix of plain <package_id>, simple <package_id@version> specifiers or full "
    "<pkg:npm/left-pad> purls.",
)
# TODO: add a --force/--reinstall flag
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
    prime_sudo(ctx, selected_managers)

    solver = Solver(packages_specs, manager_priority=manager_ids)
    packages_per_managers = solver.resolve_specs_group_by_managers()
    unmatched_packages = packages_per_managers.get(None, set())

    # Collect the label of every requested spec that no manager could install, to
    # raise a non-zero exit code at the end of the command.
    unresolved_labels: list[str] = []

    # Packages tied to a manager (purls, or a single-manager selection) install
    # concurrently across managers, serial within each (see collect_per_package). An
    # untied package needs a priority search (install with the first manager that has
    # it, skip the rest), which is cross-manager-sequential; its presence drops the
    # whole command onto the sequential path below.
    if not unmatched_packages:
        failures_lock = threading.Lock()

        def make_cooldown_task(spec, mgr):
            # cooldown_permits() already logged why; a skip is ✗ but not unresolved, so
            # it never forces a non-zero exit.
            def task() -> tuple[bool, str]:
                return False, f"{package_label(spec)} skipped in {mgr} (cooldown)"

            return task

        tasks: list[tuple[PackageManager, Callable[[], tuple[bool, str]]]] = []
        for manager_id, package_specs in packages_per_managers.items():
            if not manager_id:
                continue
            manager = pool.get(manager_id)
            mgr = theme().invoked_command(manager_id)
            permitted = cooldown_permits(manager)
            for spec in package_specs:
                if permitted:
                    task = _package_task(
                        manager,
                        spec,
                        failures_lock,
                        action=_install_action,
                        verb="install",
                        past="installed",
                        prep="with",
                        operation=Operations.install.name,
                        record_failure=lambda s: unresolved_labels.append(
                            package_label(s)
                        ),
                    )
                else:
                    task = make_cooldown_task(spec, mgr)
                tasks.append((manager, task))
        collect_per_package("Installing", "Installed", tasks)

        exit_on_failures(ctx, "install", unresolved_labels)
        return

    # Untied packages present: the priority search cannot fan out, so run sequentially
    # (see warn_jobs_ignored).
    warn_jobs_ignored(ctx)

    # Leave a per-package ✓/✗ ledger plus a persistent finisher (see OperationTrail),
    # keyed by package and its resolving manager.
    total = sum(len(specs) for specs in packages_per_managers.values())
    op = OperationTrail(selected_managers)
    installed_count = 0

    def trail(spec: Specifier, manager_id: str, status: str) -> None:
        """Map an install attempt to a `✓`/`✗` ledger line through `op`.

        `status` is `installed` (✓), or `not_found` / `failed` / `cooldown`
        (✗).
        """
        mgr = theme().invoked_command(manager_id)
        reason = {
            "installed": f"installed with {mgr}",
            "not_found": f"not found in {mgr}",
            "failed": f"failed to install with {mgr}",
            "cooldown": f"skipped in {mgr} (cooldown)",
        }[status]
        op.mark(status == "installed", f"{package_label(spec)} {reason}")

    # Install all packages deterministically tied to a specific manager.
    for manager_id, package_specs in packages_per_managers.items():
        if not manager_id:
            continue
        manager = pool.get(manager_id)
        if not cooldown_permits(manager):
            # cooldown_permits() already logged why; mark the tied packages dropped.
            for spec in package_specs:
                trail(spec, manager_id, "cooldown")
            continue
        for spec in package_specs:
            # A tied package has exactly one candidate manager, so a miss is final:
            # record it as unresolved (forcing a non-zero exit) and mark the ✗ trail.
            if _attempt_install(manager, spec):
                installed_count += 1
                trail(spec, manager_id, "installed")
            else:
                unresolved_labels.append(package_label(spec))
                trail(spec, manager_id, "failed")

    # Drop managers that cannot honor an active cooldown (once, not per package).
    eligible_managers = tuple(m for m in selected_managers if cooldown_permits(m))
    for spec in unmatched_packages:
        installed = False
        for manager in eligible_managers:
            # Is the package available on this manager? The per-attempt reason is INFO
            # narration; the ✗ trail line below names the manager that missed.
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
                    extra={"label": manager.id},
                )
                logging.info(
                    f"{spec.package_id} existence unconfirmed, "
                    "try to directly install it...",
                )
            except CLIError:
                logging.info(
                    f"Could not search for {spec.package_id}.",
                    extra={"label": manager.id},
                )
                trail(spec, manager.id, "not_found")
                continue
            else:
                if not matches:
                    logging.info(
                        f"No {spec.package_id} package found.",
                        extra={"label": manager.id},
                    )
                    trail(spec, manager.id, "not_found")
                    continue
                # Prevents any incomplete or bad implementation of exact search.
                if len(matches) != 1:
                    msg = "Exact search returned multiple packages."
                    raise ValueError(msg)

            # On a failed install, fall through to the next manager in priority order.
            if not _attempt_install(manager, spec):
                trail(spec, manager.id, "failed")
                continue
            # Stop at the first (highest-priority) manager that provides the package.
            installed = True
            installed_count += 1
            trail(spec, manager.id, "installed")
            break

        if not installed:
            unresolved_labels.append(package_label(spec))

    op.finish(installed_count == total, f"Installed {installed_count}/{total} packages")

    # Fail with a non-zero exit code if any requested package went uninstalled by every
    # selected manager.
    exit_on_failures(ctx, "install", unresolved_labels)


@mpm.command(aliases=["update"], short_help="Upgrade packages.", section=MAINTENANCE)
@option(
    "-A",
    "--all",
    is_flag=True,
    default=False,
    help="Upgrade all outdated packages. "
    "Will make the command ignore package IDs provided as parameters.",
)
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

    # Full upgrade: one ✓/✗ ledger line per manager plus a finisher (see
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
        prime_sudo(ctx, managers)
        announce = _announce_level(ctx)

        def upgrade_all_work(manager: PackageManager) -> tuple[str, dict]:
            mgr = theme().invoked_command(manager.id)
            # cooldown_permits() already logs the reason at WARNING when it blocks;
            # mark the manager ✗ without running its CLI.
            if not cooldown_permits(manager):
                return manager.id, {
                    "failed": True,
                    "label": f"{mgr} skipped (cooldown)",
                }
            logging.log(
                announce,
                "Upgrade all outdated packages...",
                extra={"label": manager.id},
            )
            before = len(manager.cli_errors)
            output = manager.upgrade()
            if output:
                logging.info(output, extra={"label": manager.id})
            return manager.id, {"errors": manager.cli_errors[before:]}

        # Full upgrade is independent per manager, so fan out concurrently with a
        # ✓/✗ trail and a success-count finisher (see collect_from_managers).
        collect_from_managers(
            "Upgrading", "Upgraded", managers, upgrade_all_work, report_state=True
        )
        ctx.exit()

    _dispatch_sourced_operation(
        ctx,
        packages_specs,
        operation=Operations.upgrade,
        action=lambda m, s: m.upgrade(s.package_id, version=s.version),
        verb="upgrade",
        past="upgraded",
        prep="with",
        label="Upgrading",
        done_label="Upgraded",
        apply_cooldown=True,
    )


@mpm.command(aliases=["uninstall"], short_help="Remove a package.", section=MAINTENANCE)
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
@pass_context
def remove(ctx, orphans, packages_specs):
    """Remove one or more packages.

    Packages recognized by multiple managers will be remove with each of them. You can
    fine-tune this behavior with more precise package specifiers (like purl) and/or
    tighter selection of managers.

    Packages unrecognized by any selected manager will be skipped.

    With `--orphans`, each package is removed together with the dependencies it alone
    pulled in, mapped to the manager's native cascade verb (``apt remove
    --auto-remove`, `pacman --remove --recursive`, `dnf autoremove``, ...). Managers
    with no such verb remove the package only.
    """

    def remove_action(manager: PackageManager, spec: Specifier) -> str | None:
        # --orphans routes to the native cascade verb, falling back to the plain
        # removal (with an INFO capability-skip) for managers that lack one. The
        # NotImplementedError is caught here so it never reaches _package_task, which
        # would otherwise record the package as a failure.
        if orphans:
            try:
                return manager.remove_orphan(spec.package_id)
            except NotImplementedError:
                logging.info(
                    "Does not implement orphan removal, removing the package only.",
                    extra={"label": manager.id},
                )
        return manager.remove(spec.package_id)

    _dispatch_sourced_operation(
        ctx,
        packages_specs,
        operation=Operations.remove,
        action=remove_action,
        verb="remove",
        past="removed",
        prep="from",
        label="Removing",
        done_label="Removed",
    )


@mpm.command(short_help="Sync local package info.", section=MAINTENANCE)
@pass_context
def sync(ctx):
    """Sync local package metadata and info from external sources."""
    managers = list(ctx.obj.selected_managers(implements_operation=Operations.sync))
    prime_sudo(ctx, managers)
    announce = _announce_level(ctx)

    # Sync is independent per manager, so fan out concurrently with a ✓/✗ trail and
    # a success-count finisher (see collect_from_managers).
    collect_from_managers(
        "Syncing",
        "Synced",
        managers,
        _maintenance_work(announce, "Sync package info...", lambda m: m.sync()),
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
    the `✓`/`✗` trail labels, so the run discloses which categories each
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


@mpm.command(short_help="Cleanup local data.", section=MAINTENANCE)
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

    prime_sudo(ctx, managers)
    announce = _announce_level(ctx)

    def cleanup_work(manager: PackageManager) -> tuple[str, dict]:
        # A bespoke variant of _maintenance_work: managers run different category
        # subsets, so both the narration and the trail label disclose each
        # manager's own dispatch (`✓ brew (cache)`).
        steps = _cleanup_steps(manager, selected, explicit_orphans)
        categories = ", ".join(category for category, _step in steps)
        logging.log(announce, f"Cleanup ({categories})...", extra={"label": manager.id})
        before = len(manager.cli_errors)
        for _category, step in steps:
            step()
        return manager.id, {
            "errors": manager.cli_errors[before:],
            "label": f"{theme().invoked_command(manager.id)} ({categories})",
        }

    # Cleanup is independent per manager, so fan out concurrently with a ✓/✗ trail
    # and a success-count finisher (see collect_from_managers).
    collect_from_managers(
        "Cleaning up",
        "Cleaned",
        managers,
        cleanup_work,
        report_state=True,
    )


@mpm.command(
    aliases=["check", "diagnose"],
    short_help="Diagnose managers health.",
    section=MAINTENANCE,
)
@pass_context
def doctor(ctx):
    """Run each manager's native self-diagnosis and relay its report.

    Read-only: nothing is modified. Each manager runs its own diagnostic verb
    (`brew doctor`, `pip check`, `pacman --database --check`, `npm doctor`,
    ...), its health is read from that command's exit code, and its report — the
    diagnosis being the product, not something `mpm` can parse — is relayed
    verbatim to `<stdout>`, one section per manager with findings.

    The trail marks each manager `✓` (healthy) or `✗` (problems found), and the
    run exits non-zero when any manager reports problems, so the command can gate a
    CI job. `-0`/`--zero-exit` keeps the exit code at `0`. Managers with no
    diagnostic verb are skipped.
    """
    managers = list(ctx.obj.selected_managers(implements_operation=Operations.doctor))
    prime_sudo(ctx, managers)
    announce = _announce_level(ctx)

    def doctor_work(manager: PackageManager) -> tuple[str, dict]:
        logging.log(announce, "Diagnose...", extra={"label": manager.id})
        healthy, report = manager.doctor()
        return manager.id, {"failed": not healthy, "report": report}

    # The diagnosis is independent per manager, so fan out concurrently with a
    # ✓/✗ trail and a success-count finisher; reports are relayed afterwards, in
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
        if report:
            echo(f"{theme().invoked_command(manager_id)}:")
            echo(report)
            echo()

    if unhealthy:
        plural = "s" if len(unhealthy) > 1 else ""
        fail_unless_zero_exit(
            ctx,
            f"{len(unhealthy)} manager{plural} reported problems "
            f"({', '.join(sorted(unhealthy))}).",
        )
