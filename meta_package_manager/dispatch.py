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
"""Cross-manager dispatch: scheduling many package managers at once.

Where {mod}`meta_package_manager.execution` runs *one* manager's CLI in one
subprocess, this module schedules *many* managers concurrently: the job-count
policy that decides sequential-vs-concurrent ({func}`effective_jobs`), the
up-front availability probe used during selection ({func}`warm_availability`),
the two spinner-wrapped fan-out primitives the CLI subcommands drive
({func}`collect_from_managers`, {func}`collect_per_package`) with their shared
{func}`dispatch` engine, the backend-lock catalog that serializes conflicting
managers ({data}`SHARED_LOCK_FAMILIES` and {func}`merge_into_lock_lanes`), and
the manager-bound `✓`/`✗` ledger ({class}`OperationTrail`) that the
concurrent and sequential paths both report through.

The generic layers live upstream in click-extra: the concurrency primitives in
{mod}`click_extra.execution` (`run_jobs`/`run_lanes` driven by
`mpm --jobs`) and the batch-reporting trail in {mod}`click_extra.spinner`
({class}`~click_extra.spinner.OperationTrail` with its
`trail_glyph`/`trail_line` atoms). This module keeps what is package-manager
policy: which managers must never overlap, how the trail binds to the pool's
`--progress` state, and when a batch collapses to a sequential pass.
"""

from __future__ import annotations

import logging
from typing import Final

from click.core import ParameterSource
from click_extra import get_current_context
from click_extra.context import JOBS
from click_extra.execution import resolve_jobs, run_jobs, run_lanes
from click_extra.spinner import OperationTrail as _OperationTrail
from click_extra.theme import get_current_theme as theme

from .execution import SPINNER_DELAY

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from click import Context
    from typing_extensions import Self

    from .manager import PackageManager


SHARED_LOCK_FAMILIES: Final[tuple[frozenset[str], ...]] = (
    frozenset({"apt", "apt-mint", "deb-get"}),
    frozenset({"brew", "cask"}),
    frozenset({"dnf", "dnf5", "yum", "zypper"}),
    frozenset({"pacman", "pacstall"}),
)
"""Managers that contend for one shared backend lock, grouped by backend.

Different managers are otherwise independent processes over disjoint state, so running
them in parallel is safe. The exception is a handful that drive a *shared* backend and
serialize on its lock:

- `apt`, `apt-mint` and `deb-get` all reach {command}`dpkg`
  (`/var/lib/dpkg/lock`).
- `brew` and `cask` are the *same* {command}`brew` binary and serialize on
  Homebrew's own update lock: two concurrent `brew update` (which {command}`mpm sync`
  issues identically for both, as the formula/cask split does not apply to it) collide,
  one failing with *"Another active Homebrew update process is already running"*.
- `dnf`, `dnf5`, `yum` and `zypper` all reach the RPM database.
- `pacman` and `pacstall` all reach the pacman database
  (`/var/lib/pacman/db.lck`).

Concurrency is safe *across* families and unsafe *within* one, just as it is unsafe
within a single manager (which is why a manager's own packages stay serial). When two
members run at once the shared lock makes them *block or fail*, never corrupt.

Enforced for the mutating fan-outs only: {func}`merge_into_lock_lanes` collapses each
family's members into a single {func}`dispatch` lane, so they run serially while
distinct families still run in parallel. The read-only queries
(`installed`/`outdated`/`search`) take no backend lock, so they keep one lane per
manager and stay fully concurrent. Members of a lane also share a command cache (see
{attr}`CLIExecutor.run_cache`), so two that resolve to a byte-identical invocation
(`brew` and `cask` for `sync` and `cleanup`) run the subprocess once.

Adding a newly-conflicting set of managers is a one-line edit here: append a
`frozenset` of their ids and both the serialization and the cache pick it up.
"""


_LOCK_FAMILY_BY_MANAGER: Final[dict[str, frozenset[str]]] = {
    manager_id: family for family in SHARED_LOCK_FAMILIES for manager_id in family
}
"""Reverse index of {data}`SHARED_LOCK_FAMILIES`: each member maps to its family.

Lets {func}`merge_into_lock_lanes` resolve a manager's mutual-exclusion group in O(1).
"""


def effective_jobs(ctx: Context | None, count: int) -> int:
    """Resolve how many worker threads to use for a batch of `count` items.

    Thin wrapper over {func}`click_extra.execution.resolve_jobs` pinning mpm's
    policy: always collapse to a single (sequential) worker at `DEBUG` verbosity,
    where coherent per-manager log narration matters more than the speed-up
    (interleaved threads would scramble it). The base helper also collapses to
    sequential with no active CLI context, for a single item, or at
    `mpm --jobs` `1`; otherwise the `mpm --jobs` value wins,
    capped at `count` (no point spinning up more workers than there are items).
    """
    return resolve_jobs(ctx, count, serial_at_debug=True)


def warm_availability(managers: Iterable[PackageManager]) -> None:
    """Probe several managers' `available` concurrently.

    Reading `available` forces a manager's `--version` detection, whose
    result (and the `cli_path` / `executable` / `version` it depends on) is
    cached on the instance. Warming the candidate set up front turns the
    sequential string of probes into a single round bounded by the slowest one,
    shaving startup latency off any command that touches many managers.

    Each manager is a distinct instance with its own cached attributes and
    subprocess, so the probes are independent and thread-safe; the GIL is released
    while each waits. The executor barrier publishes every cached value before the
    caller reads it back.

    Sized by {func}`effective_jobs`: a no-op (leaving the probes to lazy,
    sequential evaluation) without an active context, at `DEBUG` verbosity, for a
    single candidate, or at `mpm --jobs` `1`.
    """
    candidates = list(managers)
    jobs = effective_jobs(get_current_context(silent=True), len(candidates))
    if jobs <= 1:
        return
    # Reading `available` forces and caches the probe inside each worker.
    list(run_jobs(lambda manager: manager.available, candidates, jobs=jobs))


def _state_failed(data: dict) -> bool:
    """Whether a manager's result fails its `✓`/`✗` trail line.

    A non-empty `data["errors"]` (CLI errors, or a read query's error list) or an
    explicit `data["failed"]` flag (`upgrade --all`'s cooldown skips, which run
    no CLI of their own) both mark the line `✗`.
    """
    return bool(data.get("errors") or data.get("failed"))


class OperationTrail(_OperationTrail):
    """{class}`click_extra.spinner.OperationTrail` bound to the manager pool.

    The upstream class owns the two renderings (sequential echoed lines, or one
    aggregate spinner with buffered-then-streamed lines) and the interactive
    gating; this subclass supplies mpm's policy around it:

    - **Enablement follows `--progress`**, folded into each manager's
      `progress` flag by the CLI (a TTY, no serialized output, not at `DEBUG`
      verbosity): any enabled manager turns the trail on, auto-gated on an
      interactive stderr.
    - **A concurrent batch mutes the managers' own per-call spinners** (which
      would collide on stderr) for the duration of the aggregate one.
    - **`coverage` keeps the read-command semantics**: their result *table* is
      the real output and each manager keeps its per-call spinner, so the
      sequential rendering stays silent (upstream's `echo_sequential=False`).

    The ordering-bound sequential state changers (`install`'s priority search)
    construct it bare; every {func}`dispatch` batch drives it as a context
    manager.

    :param managers: the batch's managers, read for the `--progress` gate and
        (when concurrent) to mute their per-call spinners.
    :param label: present-tense verb for the running spinner ("Searching").
    :param unit: the noun counted in the spinner tally ("managers", "packages").
    :param total: how many outcomes are expected, for the `done/total` count.
    :param jobs: the worker count from {func}`effective_jobs`; `> 1` selects the
        concurrent rendering.
    :param coverage: when set, a sequential run stays silent (the caller has
        another output, its result table). Unused when concurrent.
    """

    def __init__(
        self,
        managers: Iterable[PackageManager],
        *,
        label: str = "",
        unit: str = "",
        total: int = 0,
        jobs: int = 1,
        coverage: bool = False,
    ) -> None:
        self._managers = tuple(managers)
        progress = any(manager.progress for manager in self._managers)
        super().__init__(
            label=label,
            unit=unit,
            total=total,
            jobs=jobs,
            # Progress off forces full silence; on, the upstream TTY gate decides.
            enabled=None if progress else False,
            echo_sequential=not coverage,
            delay=SPINNER_DELAY,
        )

    def __enter__(self) -> Self:
        # A single aggregate spinner stands in for the muted per-call ones.
        if self.concurrent:
            for manager in self._managers:
                manager.progress = False
        return super().__enter__()


def dispatch(
    label: str,
    done_label: str,
    unit: str,
    lanes: list[
        tuple[tuple[PackageManager, ...], list[Callable[[], tuple[bool, str]]]]
    ],
    *,
    coverage: bool = False,
    ctx: Context | None = None,
) -> None:
    """Fan a set of work *lanes* out across managers, narrating a `✓`/`✗` trail.

    The single scheduling primitive behind both {func}`collect_from_managers` and
    {func}`collect_per_package`. A *lane* is one or more managers paired with a list of
    callables; lanes run concurrently (one worker each) while a lane's own callables run
    serially, because a package manager cannot safely run two of its own invocations at
    once, nor can two managers sharing a backend lock (see {data}`SHARED_LOCK_FAMILIES`).
    A lane usually wraps a single manager; {func}`merge_into_lock_lanes` is what bundles
    a whole lock family into one, and such a lane also gets a shared command cache (see
    {attr}`CLIExecutor.run_cache`) so its members collapse identical invocations.

    Each callable does its work, records its own outcome (output to `INFO`, failures
    into a caller-owned list) and returns `(ok, message)` for the trail. The whole
    batch reports through one {class}`OperationTrail`: a per-outcome `✓`/`✗` line
    plus a finisher, behind a single aggregate spinner when concurrent (a slow batch on
    a terminal) and silent otherwise.

    Concurrency is sized by {func}`effective_jobs` (driven by `mpm --jobs`): it
    collapses to a sequential pass — preserving each manager's own per-call spinner —
    for a single lane, at `--jobs 1`, or at `DEBUG` verbosity.

    :param coverage: forwarded to {class}`OperationTrail`. Read commands set it (their
        result table is the output, so the sequential pass stays silent and the finisher
        reports coverage, ``{done_label} N {unit}``, always `✓`). Maintenance and
        state-changing commands leave it `False` (the trail *is* their output, so the
        finisher reports the success count, ``{done_label} N/M {unit}``, `✗` on any
        failure).
    :param ctx: the active click context, read only to size concurrency
        ({func}`effective_jobs`). Defaults to the current context, so a command need not
        thread it; tests pass an explicit stand-in.
    """
    total = sum(len(tasks) for _managers, tasks in lanes)
    if not total:
        return
    if ctx is None:
        ctx = get_current_context(silent=True)
    jobs = effective_jobs(ctx, len(lanes))
    managers = [manager for lane_managers, _ in lanes for manager in lane_managers]

    # A multi-manager lane is a lock family: its members share one command cache
    # for the run, so byte-identical invocations (brew and cask both running
    # `brew update`) hit the subprocess once. Each cache belongs to a single lane
    # whose tasks run serially on one worker (via run_lanes), so only that thread
    # touches it: no lock needed. Cleared in the finally below.
    shared_caches: list[tuple[tuple[PackageManager, ...], dict]] = [
        (lane_managers, {}) for lane_managers, _ in lanes if len(lane_managers) > 1
    ]
    for lane_managers, cache in shared_caches:
        for manager in lane_managers:
            manager.run_cache = cache

    try:
        with OperationTrail(
            managers,
            label=label,
            unit=unit,
            total=total,
            jobs=jobs,
            coverage=coverage,
        ) as trail:
            # Each lane's tasks run serially on one worker, marking the trail as each
            # completes; distinct lanes run concurrently, sized by `effective_jobs`.
            list(
                run_lanes(
                    lambda task: trail.mark(*task()),
                    [tasks for _managers, tasks in lanes],
                    jobs=jobs,
                )
            )

            if coverage:
                trail.finish(True, f"{done_label} {total} {unit}")
            else:
                ok = trail.ok_count
                trail.finish(ok == total, f"{done_label} {ok}/{total} {unit}")
    finally:
        for lane_managers, _ in shared_caches:
            for manager in lane_managers:
                manager.run_cache = None


def merge_into_lock_lanes(
    pairs: list[tuple[PackageManager, Callable[[], tuple[bool, str]]]],
) -> list[tuple[tuple[PackageManager, ...], list[Callable[[], tuple[bool, str]]]]]:
    """Group `(manager, task)` pairs into {func}`dispatch` lanes, one per lock family.

    Managers sharing a {data}`SHARED_LOCK_FAMILIES` entry collapse into a single lane so
    their tasks run serially (the lane is {func}`dispatch`'s unit of mutual exclusion),
    while unrelated managers each keep their own lane and run concurrently. A manager not
    in any family keys on its own id, so its tasks still group together (a manager's own
    invocations cannot overlap either). First-seen order is preserved, both across lanes
    and within a lane's task list.

    Used by the mutating fan-outs only: the state changers through
    {func}`collect_per_package`, and `sync`/`cleanup`/`upgrade --all` through
    {func}`collect_from_managers`. The read commands take no backend lock and skip this,
    keeping one lane per manager.
    """
    lanes: dict[
        object, tuple[list[PackageManager], list[Callable[[], tuple[bool, str]]]]
    ]
    lanes = {}
    for manager, task in pairs:
        key = _LOCK_FAMILY_BY_MANAGER.get(manager.id, manager.id)
        lane_managers, lane_tasks = lanes.setdefault(key, ([], []))
        if manager not in lane_managers:
            lane_managers.append(manager)
        lane_tasks.append(task)
    return [(tuple(ms), ts) for ms, ts in lanes.values()]


def collect_from_managers(
    label: str,
    done_label: str,
    managers: list[PackageManager],
    work: Callable[[PackageManager], tuple[str, dict]],
    *,
    report_state: bool = False,
    ctx: Context | None = None,
) -> list[tuple[str, dict]]:
    """Run `work(manager)` for every manager concurrently, results in input order.

    The fan-out primitive for the read-only commands (`installed`/`outdated`/
    `search`) and the independent maintenance commands (`sync`/`cleanup`/
    `upgrade --all`). It adapts each manager into a {func}`dispatch` unit that runs
    `work` and stashes the `(id, data)` result in input position, so the returned
    list mirrors `managers` regardless of completion order. The maintenance commands
    (`report_state`) then merge lock-family members into shared serial lanes
    ({func}`merge_into_lock_lanes`); the read commands keep one lane per manager.

    `work` returns this manager's `(id, data)`; it must handle its own
    {class}`meta_package_manager.execution.CLIError` (each manager owns its
    subprocess and error list, so the call is thread-safe per manager). A truthy
    `data["errors"]` (or `data["failed"]`) marks that manager's trail line `✗`;
    an optional `data["label"]` overrides its text (`upgrade --all` uses it for
    cooldown skips).

    :param report_state: maintenance commands set it (their only output is the trail).
        It flips the finisher to a success count, keeps the trail in the sequential
        fallback, and turns on lock-family serialization. Read commands leave it
        `False`: their table is the output, so the sequential fallback is silent and
        the finisher reports coverage. Passed to {func}`dispatch` as the inverse of
        `coverage`.
    """
    results: list[tuple[str, dict]] = [("", {})] * len(managers)

    def make_unit(
        index: int, manager: PackageManager
    ) -> Callable[[], tuple[bool, str]]:
        def unit() -> tuple[bool, str]:
            manager_id, data = work(manager)
            results[index] = (manager_id, data)
            text = data.get("label") or theme().invoked_command(manager_id)
            return not _state_failed(data), text

        return unit

    pairs = [(manager, make_unit(i, manager)) for i, manager in enumerate(managers)]
    # Mutating fan-outs (report_state) serialize lock families into shared lanes; the
    # read commands take no backend lock and keep one lane per manager.
    lanes: list[tuple[tuple[PackageManager, ...], list[Callable[[], tuple[bool, str]]]]]
    if report_state:
        lanes = merge_into_lock_lanes(pairs)
    else:
        lanes = [((manager,), [unit]) for manager, unit in pairs]
    dispatch(label, done_label, "managers", lanes, coverage=not report_state, ctx=ctx)
    return results


def collect_per_package(
    label: str,
    done_label: str,
    tasks: list[tuple[PackageManager, Callable[[], tuple[bool, str]]]],
    *,
    ctx: Context | None = None,
) -> None:
    """Run per-package operations across managers concurrently, serial within each.

    The fan-out primitive for the ordering-free state changers that act on many
    (package, manager) pairs: `remove`, `upgrade <packages>`, `restore` and the
    manager-tied specs of `install`. Takes a flat list of `(manager, task)` pairs
    and groups them into lanes by lock family ({func}`merge_into_lock_lanes`) — so a
    manager's own packages, and any lock-family peers, stay serial while unrelated
    managers run in parallel — then drives {func}`dispatch`. Each task returns
    `(ok, message)` after doing its CLI call and recording its own outcome. The
    unmatched-package priority search of `install` is *not* routed here: it has genuine
    cross-manager ordering (stop at the first manager that has the package) and stays
    sequential on its own.
    """
    dispatch(label, done_label, "packages", merge_into_lock_lanes(tasks), ctx=ctx)


def warn_jobs_ignored(ctx: Context) -> None:
    """Note that `--jobs` does not parallelize this run.

    Only `install` with at least one *untied* package reaches this: those packages
    need a priority search (install with the first manager that has the package, skip
    the rest), which is cross-manager-sequential, so the whole command runs serially.
    The other state changers (`remove`, `upgrade <packages>`, `restore`, and
    `install` of fully manager-tied specs) now fan out through
    {func}`collect_per_package`. When the user explicitly raised `mpm --jobs`
    above `1`, say so once at `INFO`: the request simply has no effect on this
    run, which is narration, not a problem.
    """
    if ctx.meta.get(JOBS, 1) <= 1:
        return
    if ctx.find_root().get_parameter_source("jobs") not in (
        ParameterSource.COMMANDLINE,
        ParameterSource.ENVIRONMENT,
    ):
        return
    logging.info(
        "This command dispatches managers sequentially by priority; "
        "--jobs does not parallelize it.",
    )
