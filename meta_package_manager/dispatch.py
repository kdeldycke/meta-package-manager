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
the two progress-wrapped fan-out primitives the CLI subcommands drive
({func}`collect_from_managers`, {func}`collect_per_package`) with their shared
{func}`dispatch` engine, the backend-lock catalog that serializes conflicting
managers ({data}`SHARED_LOCK_FAMILIES` and {func}`merge_into_lock_lanes`), and
the manager-bound `✓`/`✗` ledger ({class}`OperationTrail`) that the
concurrent and sequential paths both report through.

The generic layers live upstream in click-extra: the concurrency primitives in
{mod}`click_extra.execution` (`run_lanes` driven by
`mpm --jobs`) and the batch-reporting trail in {mod}`click_extra.spinner`
({class}`~click_extra.spinner.OperationTrail` with its
`trail_glyph`/`trail_line` atoms). This module keeps what is package-manager
policy: which managers must never overlap, how the trail binds to the pool's
`--progress` state, and when a batch collapses to a sequential pass.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final

from click.core import ParameterSource
from click_extra import get_current_context
from click_extra.context import JOBS
from click_extra.execution import resolve_jobs, run_lanes
from click_extra.spinner import OperationTrail as _OperationTrail
from click_extra.theme import get_current_theme as theme

from .execution import SPINNER_DELAY

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from click import Context
    from typing_extensions import Self

    from .manager import PackageManager


@dataclass(frozen=True)
class LockFamily:
    """A set of managers contending for one backend lock."""

    backend: str
    """Short name of the contended resource, labelling the family in the docs.

    Rendered as the middle level of
    `meta_package_manager._docs.lock_families_sankey()` and as the first
    column of `meta_package_manager._docs.lock_families_table()`, so it
    reads as a thing managers queue on rather than as a tool: *pacman
    database*, not *pacman*.

    That phrasing is also load-bearing for the diagram. Mermaid identifies a
    sankey node by its label alone, so a family named after a member (`pkg`,
    `conda`, `pacman` and `scoop` all name both) would fold the two levels into
    one self-linked node. `test_lock_family_backends_are_distinct` holds every
    name clear of the pool.
    """

    members: frozenset[str]
    """Manager ids that must never mutate at the same time."""

    contention: str
    """Why they collide, written to complete the sentence *"`mpm` never runs X at the
    same time as Y: …"*.

    Rendered on every member's own documentation page by
    `meta_package_manager._docs.manager_concurrency()`, so it addresses a user
    of those managers rather than a reader of this module: keep it to the fact and
    its consequence, and leave the maintenance rationale to the notes below.
    """


SHARED_LOCK_FAMILIES: Final[tuple[LockFamily, ...]] = (
    LockFamily(
        "dpkg lock",
        frozenset({"apt", "apt-mint", "deb-get", "nala", "pacstall"}),
        "they all install through `dpkg` and serialize on its `/var/lib/dpkg/lock`",
    ),
    LockFamily(
        "Homebrew update lock",
        frozenset({"brew", "cask"}),
        "they are the same `brew` binary, and two concurrent `brew update` collide "
        "on Homebrew's own update lock",
    ),
    LockFamily(
        "conda environment prefix",
        frozenset({"conda", "mamba", "micromamba"}),
        "they act on one environment prefix and one package cache, and `conda` "
        "honors none of the locks `mamba` takes on them",
    ),
    LockFamily(
        "RPM database",
        frozenset({"dnf", "dnf5", "urpmi", "yum", "zypper"}),
        "they all reach the RPM database",
    ),
    LockFamily(
        "pacman database",
        frozenset({"pacaur", "pacman", "pamac", "paru", "pikaur", "trizen", "yay"}),
        "they all reach the pacman database (`/var/lib/pacman/db.lck`), and two of "
        "them mutating at once fail to init their transaction",
    ),
    LockFamily(
        "pkg install database",
        frozenset({"pkg", "ports"}),
        "`ports` keeps no registry of its own and registers what it builds through "
        "`pkg`, whose advisory lock on that shared install database refuses a "
        "second writer",
    ),
    LockFamily(
        "Scoop tree",
        frozenset({"scoop", "sfsu"}),
        "they work on the same `~/scoop` tree, `sfsu` delegating its mutating "
        "operations to the `scoop` binary itself",
    ),
)
"""Managers that contend for one shared backend lock, grouped by backend.

Different managers are otherwise independent processes over disjoint state, so running
them in parallel is safe. The exception is a handful that drive a *shared* backend and
serialize on its lock:

- `apt`, `apt-mint`, `deb-get`, `nala` and `pacstall` all reach {command}`dpkg`
  (`/var/lib/dpkg/lock`). `pacstall` belongs here despite its `pac` prefix and its
  AUR-inspired design: it builds its pacscripts into `.deb` archives and installs
  those, so it contends with the Debian family and never touches pacman's database.
- `brew` and `cask` are the *same* {command}`brew` binary and serialize on
  Homebrew's own update lock: two concurrent `brew update` (which {command}`mpm sync`
  issues identically for both, as the formula/cask split does not apply to it) collide,
  one failing with *"Another active Homebrew update process is already running"*.
- `conda`, `mamba` and `micromamba` act on one environment prefix and one package
  cache. This is the family that does *not* get the guarantee below: mamba takes a
  real lock on the prefix and on every cache directory for the length of a
  transaction, and conda honors none of them, its own locking covering the repodata
  cache alone. Concurrent runs corrupt rather than block, which upstream closed as
  not planned ([conda/conda#13037](https://github.com/conda/conda/issues/13037)).
  Serializing them here is what keeps that out of reach.
- `dnf`, `dnf5`, `yum`, `zypper` and `urpmi` all reach the RPM database. `urpmi`
  fronts `librpm` directly, having no listing of its own, and the Mandriva lineage
  it serves ships `dnf` alongside it, so the two genuinely coexist on one host.
- `pacman` and the AUR helpers `pacaur`, `pamac`, `paru`, `pikaur`, `trizen` and
  `yay` all reach the pacman database (`/var/lib/pacman/db.lck`). The helpers are
  front-ends rather than reimplementations: each shells out to `sudo pacman` for the
  privileged steps, `pamac` reaching the same `libalpm` through Manjaro's `libpamac`.
  Two of them mutating at once fail to init their transaction.
- `pkg` and `ports` share the install database `pkg` maintains, which every mutating
  operation but `sync` reaches: `ports` has no registry of its own, builds from
  `/usr/ports` and registers the result through `pkg`, whose advisory lock on that
  database refuses a second writer. Their `sync` is the one pair that would not
  collide, refreshing a git tree and a package catalog respectively, and is
  serialized along with the rest rather than splitting the family per operation.
- `scoop` and `sfsu` work on the same `~/scoop` tree. sfsu reimplements Scoop's read
  paths only, delegating `install`, `remove` and both upgrades to the `scoop` binary
  itself, so those are literally the same command twice; its own `update` and
  `cleanup` then reach the same buckets and cache Scoop's do. Concurrent bucket
  refreshes are two `git pull` in one repository, which fails on the index lock.

`dkp-pacman` is deliberately *not* in the pacman family, and it is the one exclusion
worth stating: it is `Pacman` by inheritance and would look like an oversight. But
devkitPro ships it precisely so it can sit beside a distribution's own `pacman`
without colliding, pointed at its own repositories and its own database, so it
contends with nothing.

`pkcon` is the case this model cannot express, and it is left out knowingly rather
than filed under a guess. PackageKit is a client for whatever backend the host
provides (apt, dnf, zypp, alpm), so the family it belongs to is a property of the
machine rather than of the manager, and a `frozenset` here is fixed at import. It
needs no protection from *itself*, `packagekitd` queuing its own transactions, but a
`pkcon` mutation still contends with a native manager mpm drives in the same run.
Expressing that would mean resolving the backend at dispatch time.

Concurrency is safe *across* families and unsafe *within* one, just as it is unsafe
within a single manager (which is why a manager's own packages stay serial). For every
family above *except* the conda one, two members running at once *block or fail*
rather than corrupt: each backend holds a real lock and the loser is told so. That is
a property of those backends rather than of this mechanism, so a family added later
earns the guarantee only by inspection, and conda is the standing proof that some do
not.

Enforced for the mutating fan-outs only: {func}`merge_into_lock_lanes` collapses each
family's members into a single {func}`dispatch` lane, so they run serially while
distinct families still run in parallel. The read-only queries
(`installed`/`outdated`/`search`) take no backend lock, so they keep one lane per
manager and stay fully concurrent. Members of a lane also share a command cache (see
{attr}`~meta_package_manager.execution.CLIExecutor.run_cache`), so two that resolve
to a byte-identical invocation (`brew` and `cask` for `sync` and `cleanup`) run the
subprocess once.

Adding a newly-conflicting set of managers is one entry here: a {class}`LockFamily`
naming the backend and its members, after which the serialization, the command cache,
the *Concurrency* section of every member's documentation page and both renderings of
`docs/concurrency.md` all pick it up.
"""


FAN_OUT_CONCURRENT: Final[str] = "concurrent"
"""Every selected manager runs at once, one {func}`dispatch` lane each."""

FAN_OUT_GROUPED: Final[str] = "grouped"
"""Same, but {data}`SHARED_LOCK_FAMILIES` members are merged into one lane."""

FAN_OUT_SEQUENTIAL: Final[str] = "sequential"
"""One manager at a time, whatever `mpm --jobs` says."""

FAN_OUT_NONE: Final[str] = "none"
"""Runs no package operation, so there is nothing to spread."""


@dataclass(frozen=True)
class FanOut:
    """How one way of invoking a subcommand spreads over the selected managers."""

    invocation: str
    """The subcommand, plus whichever argument changes the answer.

    `install` appears twice: a package tied to a manager rides the per-package
    fan-out, while one left untied needs the priority search that cannot be
    parallelized.
    """

    mode: str
    """One of the four `FAN_OUT_*` constants above."""

    @property
    def command(self) -> str:
        """Bare subcommand name, as the CLI registers it."""
        return self.invocation.split(" ", 1)[0]


COMMAND_FAN_OUT: Final[tuple[FanOut, ...]] = (
    FanOut("cleanup", FAN_OUT_GROUPED),
    FanOut("config-template", FAN_OUT_NONE),
    FanOut("doctor", FAN_OUT_GROUPED),
    FanOut("dump", FAN_OUT_CONCURRENT),
    FanOut("help", FAN_OUT_NONE),
    FanOut("install", FAN_OUT_GROUPED),
    FanOut("install <untied package>", FAN_OUT_SEQUENTIAL),
    FanOut("installed", FAN_OUT_CONCURRENT),
    FanOut("managers", FAN_OUT_NONE),
    FanOut("orphans", FAN_OUT_CONCURRENT),
    FanOut("outdated", FAN_OUT_CONCURRENT),
    FanOut("remove", FAN_OUT_GROUPED),
    FanOut("restore", FAN_OUT_GROUPED),
    FanOut("sbom", FAN_OUT_CONCURRENT),
    FanOut("search", FAN_OUT_CONCURRENT),
    FanOut("sync", FAN_OUT_GROUPED),
    FanOut("upgrade", FAN_OUT_GROUPED),
    FanOut("which", FAN_OUT_NONE),
)
"""Fan-out mode of every `mpm` subcommand, rendered on `docs/concurrency.md`.

The three fan-out shapes above are visible from inside this module; which
subcommand takes which is not, being an argument at each call site. This is
where the two meet, so a reader can answer *"does this command parallelize?"*
without following `report_state=True` through four CLI modules.

Kept complete rather than restricted to the commands that fan out:
`test_fan_out_covers_every_subcommand` holds it equal to the CLI's own command
list, so a new subcommand fails the suite until someone decides its mode. The
{data}`FAN_OUT_NONE` entries are that decision recorded, and
`meta_package_manager._docs.concurrency_table()` leaves them out of the
rendered table.

```{caution}
Hand-maintained, and the one thing here that can drift from the code silently.
A subcommand switching between {func}`collect_from_managers` and
{func}`collect_per_package`, or gaining `report_state=True`, has to be
reflected in the same commit: no test can read the mode back off a call site.
```
"""


_LOCK_FAMILY_BY_MANAGER: Final[dict[str, LockFamily]] = {
    manager_id: family
    for family in SHARED_LOCK_FAMILIES
    for manager_id in family.members
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


def probe_signature(manager: PackageManager) -> tuple:
    """Static signature of the command `manager`'s version probe would spawn.

    Built from class attributes alone: no filesystem lookup, no subprocess. Two
    managers sharing a signature search the same directories for the same binary
    names and pass it the same arguments, so their probes *may* resolve to a
    byte-identical command line. `brew` and `cask` do, and so do `uv`/`uvx` and
    `yarn`/`yarn-berry`.

    Deliberately conservative in the safe direction. It never splits two managers
    that would spawn the same command, which is what
    {func}`merge_into_probe_lanes` needs to put them on one lane; it may however
    merge two that turn out to differ (the Zsh plugin managers all probe `zsh`,
    some with `--version` and some with `version`). A wrong merge costs the two a
    shared lane, where the second simply misses the cache and spawns as it would
    have anyway.

    Not the resolved command line, on purpose: resolving it means walking `PATH`
    for every candidate up front, which measured slower than the redundant
    subprocesses it would save.
    """
    return (
        tuple(manager.cli_search_path),
        tuple(manager.cli_names or ()),
        manager.version_cli,
        tuple(manager.version_cli_options),
    )


def merge_into_probe_lanes(
    managers: Iterable[PackageManager],
) -> list[tuple[PackageManager, ...]]:
    """Group `managers` into {func}`warm_availability` lanes by {func}`probe_signature`.

    The probe counterpart of {func}`merge_into_lock_lanes`: managers whose version
    probe may resolve to the same command line land on one lane and run serially,
    while unrelated managers keep a lane each and run concurrently. Lanes come out
    in first-seen order, so a run is reproducible.
    """
    lanes: dict[tuple, list[PackageManager]] = {}
    for manager in managers:
        lanes.setdefault(probe_signature(manager), []).append(manager)
    return [tuple(lane) for lane in lanes.values()]


def warm_availability(managers: Iterable[PackageManager]) -> None:
    """Probe several managers' `available` concurrently.

    Reading `available` forces a manager's `--version` detection, whose
    result (and the `cli_path` / `executable` / `version` it depends on) is
    cached on the instance. Warming the candidate set up front turns the
    sequential string of probes into a single round bounded by the slowest one,
    shaving startup latency off any command that touches many managers.

    Managers on distinct lanes are distinct instances with their own cached
    attributes and subprocess, so their probes are independent and thread-safe; the
    GIL is released while each waits. The executor barrier publishes every cached
    value before the caller reads it back.

    Probes run in {func}`merge_into_probe_lanes` lanes rather than one flat batch,
    so the managers that would spawn a byte-identical `--version` call take turns
    on one worker and share a
    {attr}`~meta_package_manager.execution.CLIExecutor.run_cache`: the first spawns,
    the rest replay its result. That is the same mechanism {func}`dispatch` gives a
    lock family, and it needs the lane for the same reason — a cache handed to
    managers running concurrently would just race them both into spawning.

    Sized by {func}`effective_jobs` over the *lane* count: a no-op (leaving the
    probes to lazy, sequential evaluation) without an active context, at `DEBUG`
    verbosity, for a single lane, or at `mpm --jobs` `1`.
    """
    lanes = merge_into_probe_lanes(managers)
    jobs = effective_jobs(get_current_context(silent=True), len(lanes))
    if jobs <= 1:
        return

    # Restore whatever each manager carried instead of forcing `None` back: the cache
    # is scoped to this round, and a caller that installed one of its own keeps it.
    restore: list[tuple[PackageManager, dict | None]] = []
    for lane in lanes:
        if len(lane) < 2:
            continue
        shared_cache: dict = {}
        for manager in lane:
            restore.append((manager, manager.run_cache))
            manager.run_cache = shared_cache

    try:
        # Reading `available` forces and caches the probe inside each worker.
        list(run_lanes(lambda manager: manager.available, lanes, jobs=jobs))
    finally:
        # Unwound in reverse so the *first* value recorded for a manager is the one
        # that survives, should the same instance ever be handed in twice.
        for manager, previous_cache in reversed(restore):
            manager.run_cache = previous_cache


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
    aggregate indicator with buffered-then-streamed lines) and the interactive
    gating; this subclass supplies mpm's policy around it:

    - **Enablement follows `--progress`**, folded into each manager's
      `progress` flag by the CLI (a TTY, no serialized output, not at `DEBUG`
      verbosity): any enabled manager turns the trail on, auto-gated on an
      interactive stderr.
    - **A concurrent batch mutes the managers' own per-call spinners** (which
      would collide on stderr) for the duration of the aggregate one.
    - **A concurrent batch's aggregate indicator is a determinate progress
      bar**, not an indeterminate spinner: every {func}`dispatch` batch counts
      its work up front (one task per manager, or per package-manager pair), so
      the bar always has a length to render against.
    - **`coverage` keeps the read-command semantics**: their result *table* is
      the real output and each manager keeps its per-call spinner, so the
      sequential rendering stays silent (upstream's `echo_sequential=False`).

    The ordering-bound sequential state changers (`install`'s priority search)
    construct it bare; every {func}`dispatch` batch drives it as a context
    manager.

    :param managers: the batch's managers, read for the `--progress` gate and
        (when concurrent) to mute their per-call spinners.
    :param label: present-tense verb for the running indicator ("Searching").
    :param unit: the noun counted in the indicator tally ("managers",
        "packages").
    :param total: how many outcomes are expected, for the `done/total` count and
        the progress bar's length.
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
            # A determinate bar needs a length, so fall back to the indeterminate
            # spinner for the (unused) concurrent-without-a-total case.
            progress_bar=jobs > 1 and total > 0,
            # Progress off forces full silence; on, the upstream TTY gate decides.
            enabled=None if progress else False,
            echo_sequential=not coverage,
            delay=SPINNER_DELAY,
        )

    def __enter__(self) -> Self:
        # A single aggregate indicator stands in for the muted per-call spinners.
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
    {attr}`~meta_package_manager.execution.CLIExecutor.run_cache`) so its members
    collapse identical invocations.

    Each callable does its work, records its own outcome (output to `INFO`, failures
    into a caller-owned list) and returns `(ok, message)` for the trail. The whole
    batch reports through one {class}`OperationTrail`: a per-outcome `✓`/`✗` line
    plus a finisher, behind a single aggregate progress bar when concurrent (a slow
    batch on a terminal) and silent otherwise.

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
