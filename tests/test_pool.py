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

from __future__ import annotations

import inspect
import itertools
import threading
from datetime import timedelta
from importlib import import_module
from pathlib import Path

import click
import pytest
from click_extra.context import JOBS, VERBOSITY_LEVEL
from click_extra.logging import LogLevel

import meta_package_manager
from meta_package_manager.capabilities import Delegate
from meta_package_manager.cli import mpm
from meta_package_manager.cooldown import CooldownPolicy
from meta_package_manager.dispatch import (
    SHARED_LOCK_FAMILIES,
    merge_into_probe_lanes,
    warm_availability,
)
from meta_package_manager.labels import MANAGER_LABEL_GROUPS
from meta_package_manager.manager import PackageManager
from meta_package_manager.managers.pacman import Pacman
from meta_package_manager.pool import manager_classes, pool

from .conftest import (
    default_manager_ids,
    maintained_manager_ids,
    unsupported_manager_ids,
)

""" Test the pool and its content. """


def test_manager_definition_inventory():
    """Check all classes implementing a package manager are accounted for in the
    pool."""
    found_classes = set()

    # Search for manager definitions in the managers subfolder.
    for py_file in Path(inspect.getfile(meta_package_manager)).parent.glob(
        "managers/*.py"
    ):
        module = import_module(
            f"meta_package_manager.managers.{py_file.stem}", package=__package__
        )
        for _, klass in inspect.getmembers(module, inspect.isclass):
            if issubclass(klass, PackageManager) and not klass.virtual:
                found_classes.add(klass)

    assert sorted(map(str, found_classes)) == sorted(map(str, manager_classes))


def test_manager_classes_order():
    """Check manager classes are ordered by their IDs."""
    assert [c.__name__ for c in manager_classes] == sorted(
        (c.__name__ for c in manager_classes), key=str.casefold
    )


def test_manager_count():
    """Check all implemented package managers are accounted for, and unique."""
    assert len(manager_classes) == 81
    # Fifty-four extra beyond the built-in classes: the bundled config-defined
    # managers (apt-cyg, basalt, bob, bpkg, bun, cargo, cave, choco, chromebrew, claude-code-plugins,
    # clib, cpan, elan, emacs, fink, gcloud, getnf, gh-ext, haxelib, jpm, julia, juliaup, krew,
    # macports, micro, ollama, opam, opkg, pamac, pearl, pi, pkg-tools, pipxu, pkgin, pkgm, platformio-core, pyenv,
    # raco, rustup, skills, slapt-get, soar, sorcery, steamcmd, stew, swupd, tlmgr,
    # topgrade, urpmi, vscode, vscodium, xcodes, yazi, zerobrew), shipped as
    # package data and loaded into the pool at construction.
    assert len(pool) == 135
    assert len(pool) == len(pool.all_manager_ids)
    assert pool.all_manager_ids == tuple(sorted(set(pool)))


def test_shared_lock_families_are_disjoint():
    """No manager may belong to two lock families, or its lane grouping is ambiguous."""
    seen: set[str] = set()
    for family in SHARED_LOCK_FAMILIES:
        overlap = seen & family.members
        assert not overlap, f"managers in more than one lock family: {overlap}"
        seen |= family.members


def test_shared_lock_family_members_exist_in_pool():
    """Every lock-family member must be a real manager id (catches typos)."""
    for manager_id in set().union(*(f.members for f in SHARED_LOCK_FAMILIES)):
        assert manager_id in pool.all_manager_ids


def test_lock_families_nest_in_label_groups():
    """Every lock family must sit inside a single ecosystem label group.

    The two constants answer different questions. {data}`MANAGER_LABEL_GROUPS` groups
    managers by the packaging ecosystem an issue lands in, {data}`SHARED_LOCK_FAMILIES`
    the ones that cannot run at once on a real host. The implication runs one way only:
    contending for a backend lock means sharing that backend's ecosystem, so a lock
    family is always contained in a label group.

    Never the reverse, and the gaps are the point: `fink` and `opkg` speak dpkg through
    databases of their own, `zerobrew` has its own prefix and `dkp-pacman` its own
    repositories, while `pypi-based`, `npm-based` and the plugin-manager groups share a
    registry or a host program rather than any lock at all. Asserting equality here
    would be asserting those four facts away.

    Catches a manager wired into a lock family but forgotten in the label groups, which
    is what it caught for `nala`.
    """
    for family in SHARED_LOCK_FAMILIES:
        assert any(
            family.members <= group for group in MANAGER_LABEL_GROUPS.values()
        ), (
            f"lock family {sorted(family.members)} is not contained in any ecosystem "
            "label group"
        )


def test_delegating_managers_share_their_target_lock():
    """A manager delegating an operation to another's CLI runs that manager's own
    binary against that manager's own state, so the two must serialize.

    The delegation is declared in the class body ({class}`Delegate`), which makes
    this derivable rather than a list to keep in step: wiring a new delegate without
    a lock family fails here.
    """
    family_of = {mid: f for f in SHARED_LOCK_FAMILIES for mid in f.members}
    id_of = {type(pool[manager_id]): manager_id for manager_id in pool.all_manager_ids}
    for manager_id in pool.all_manager_ids:
        for klass in type(pool[manager_id]).__mro__:
            for attribute in vars(klass).values():
                if not isinstance(attribute, Delegate):
                    continue
                target = id_of[attribute.source_class]
                sharing = family_of.get(manager_id)
                assert sharing and target in sharing.members, (
                    f"{manager_id} delegates to {target} but they do not share a "
                    "lock family"
                )


def test_pacman_subclasses_share_the_pacman_lock():
    """Every manager inheriting from `Pacman` drives pacman's own database, so it
    must serialize with the rest of that family.

    `dkp-pacman` is the sole exemption: devkitPro ships it to sit beside a
    distribution's `pacman` with its own repositories and database, so it contends
    with nothing. Any *other* subclass missing from the family is the bug this
    catches, which is how the AUR helpers went unserialized through `7.6.1`.

    Inheritance is a sufficient signal, never a necessary one: `pamac` reaches the
    same `libalpm` through a bundled definition and is covered by the family
    without appearing here.
    """
    family = next(f for f in SHARED_LOCK_FAMILIES if "pacman" in f.members).members
    for manager_id in pool.all_manager_ids:
        if manager_id == "dkp-pacman" or not isinstance(pool[manager_id], Pacman):
            continue
        assert manager_id in family, (
            f"{manager_id} inherits from Pacman but is missing from its lock family"
        )


def test_cached_pool():
    assert pool == pool  # noqa: PLR0124
    assert pool is pool  # noqa: PLR0124


@maintained_manager_ids
def test_maintained_managers(manager_id):
    assert pool[manager_id].unmaintained is False


@default_manager_ids
def test_supported_managers(manager_id):
    assert pool[manager_id].supported is True


@unsupported_manager_ids
def test_unsupported_managers(manager_id):
    assert pool[manager_id].supported is False


def test_manager_groups():
    """Test relationships between manager groups."""
    assert set(pool.maintained_manager_ids).issubset(pool.all_manager_ids)
    assert set(pool.default_manager_ids).issubset(pool.all_manager_ids)
    assert set(pool.unsupported_manager_ids).issubset(pool.all_manager_ids)

    assert set(pool.default_manager_ids).issubset(pool.maintained_manager_ids)
    assert set(pool.unsupported_manager_ids).issubset(pool.maintained_manager_ids)

    assert len(pool.default_manager_ids) + len(pool.unsupported_manager_ids) == len(
        pool.maintained_manager_ids,
    )
    assert (
        tuple(sorted(set(pool.default_manager_ids).union(pool.unsupported_manager_ids)))
        == pool.maintained_manager_ids
    )


DERIVED_EXTRA_OPTIONS = frozenset({"cooldown_policy"})
"""Extra options computed from another flag rather than declared as one.

`cooldown_policy` is resolved from the `--cooldown` union and the
{mod}`meta_package_manager.cooldown` configuration (see
{func}`meta_package_manager.cooldown.resolve_cooldown`): the manager-level
attribute has no CLI flag of its own, only the per-manager override."""


def test_extra_option_allowlist():
    cli_params = {opt.name for opt in mpm.params}
    assert pool.ALLOWED_EXTRA_OPTION - DERIVED_EXTRA_OPTIONS <= cli_params


selection_cases = {
    # Selection-logic cases pass `drop_not_found=False` so they test only
    # how `keep`/`drop` plumbing handles ordering, deduplication and
    # collection types, without depending on whether the named managers
    # have a real binary on PATH.  Hermetic builders (Guix, Nixpkgs, etc.)
    # otherwise see these cases return empty tuples because `uv` and
    # `gem` are not installed.
    #
    # Availability-dependent expectations are wrapped in a lambda and resolved
    # inside the test: materializing them here would fire a live version probe
    # per manager at collection time, and under xdist a probe flapping between
    # workers (or a binary locked mid-spawn, a Windows classic) makes their
    # collected parametrize lists diverge, which aborts the whole session.
    "single_selector": (
        {"keep": ("uv",), "drop_not_found": False},
        ("uv",),
    ),
    "list_input": (
        {"keep": ["uv"], "drop_not_found": False},
        ("uv",),
    ),
    "set_input": (
        {"keep": {"uv"}, "drop_not_found": False},
        ("uv",),
    ),
    "empty_selector": (
        {"keep": (), "drop_not_found": False},
        (),
    ),
    "duplicate_selectors": (
        {"keep": ("uv", "uv"), "drop_not_found": False},
        ("uv",),
    ),
    "multiple_selectors": (
        {"keep": ("uv", "gem"), "drop_not_found": False},
        ("uv", "gem"),
    ),
    "ordered_selectors": (
        {"keep": ("gem", "uv"), "drop_not_found": False},
        ("gem", "uv"),
    ),
    "single_exclusion": (
        {"drop": {"uv"}},
        lambda: tuple(
            mid
            for mid in pool.all_manager_ids
            if pool[mid].supported and pool[mid].available and mid != "uv"
        ),
    ),
    "duplicate_exclusions": (
        {"drop": ("uv", "uv")},
        lambda: tuple(
            mid
            for mid in pool.all_manager_ids
            if pool[mid].supported and pool[mid].available and mid != "uv"
        ),
    ),
    "multiple_exclusions": (
        {"drop": ("uv", "gem")},
        lambda: tuple(
            mid
            for mid in pool.all_manager_ids
            if pool[mid].supported and pool[mid].available and mid not in ("uv", "gem")
        ),
    ),
    "selector_priority": (
        {"keep": {"uv"}, "drop": {"gem"}, "drop_not_found": False},
        ("uv",),
    ),
    "exclusion_override": (
        {"keep": {"uv"}, "drop": {"uv"}, "drop_not_found": False},
        (),
    ),
    "default_selection": (
        {},
        lambda: tuple(
            mid
            for mid in pool.all_manager_ids
            if pool[mid].supported and pool[mid].available
        ),
    ),
    "explicit_default_selection": (
        {"keep": None, "drop": None},
        lambda: tuple(
            mid
            for mid in pool.all_manager_ids
            if pool[mid].supported and pool[mid].available
        ),
    ),
    "keep_unmaintained": (
        {"keep_unmaintained": True},
        lambda: tuple(mid for mid in pool.all_manager_ids if pool[mid].available),
    ),
    "drop_unmaintained": (
        {"keep_unmaintained": False},
        lambda: tuple(
            mid
            for mid in pool.all_manager_ids
            if not pool[mid].unmaintained
            and pool[mid].supported
            and pool[mid].available
        ),
    ),
    "keep_unsupported": (
        {"keep_unsupported": True},
        lambda: tuple(mid for mid in pool.all_manager_ids if pool[mid].available),
    ),
    "drop_unsupported": (
        {"keep_unsupported": False},
        lambda: tuple(
            mid
            for mid in pool.all_manager_ids
            if pool[mid].supported and pool[mid].available
        ),
    ),
    "drop_not_found": (
        {"drop_not_found": True},
        lambda: tuple(
            mid
            for mid in pool.all_manager_ids
            if not pool[mid].unmaintained
            and pool[mid].supported
            and pool[mid].available
        ),
    ),
    "keep_not_found": (
        {"drop_not_found": False},
        tuple(
            mid
            for mid in pool.all_manager_ids
            if not pool[mid].unmaintained and pool[mid].supported
        ),
    ),
}


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    tuple(
        pytest.param(kwargs, expected, id=test_id)
        for test_id, (kwargs, expected) in selection_cases.items()
    ),
)
def test_select_managers(kwargs, expected):
    """We use tuple everywhere so we can check that select_managers() conserve the
    original order."""
    if callable(expected):
        # Availability-dependent case: see the comment atop selection_cases.
        expected = expected()
    selection = pool._select_managers(**kwargs)
    assert tuple(m.id for m in selection) == expected


def test_select_managers_timeout_stamping():
    """The user's `--timeout` lands on every selected manager even when
    unavailable ones are kept (`mpm managers`), whose version probes fire
    lazily at rendering time, after selection: an unstamped instance would fall
    back to the read-only default and let a wedged binary hold each table row
    for 120 seconds. A per-manager `[mpm.managers.<id>]` override keeps
    precedence over the global option.
    """
    originals = {mid: pool[mid].timeout for mid in ("gem", "uv")}
    try:
        selection = pool._select_managers(
            keep=("gem", "uv"),
            drop_not_found=False,
            timeout=987,
        )
        assert [manager.timeout for manager in selection] == [987, 987]

        pool.overridden_fields.setdefault("gem", set()).add("timeout")
        try:
            selection = pool._select_managers(
                keep=("gem", "uv"),
                drop_not_found=False,
                timeout=123,
            )
            assert [manager.timeout for manager in selection] == [987, 123]
        finally:
            pool.overridden_fields["gem"].discard("timeout")
    finally:
        for mid, value in originals.items():
            pool[mid].timeout = value


def test_select_managers_cooldown_policy_keeps_precedence():
    """A per-manager `cooldown_policy` override pins that manager's enforcement
    posture, so the global policy resolved from `--cooldown` must not clobber
    it: `[mpm.managers.<id>] cooldown_policy = "best-effort"` keeps running
    that one manager unguarded while the rest stay fail-closed.
    """
    manager = pool["gem"]
    original = manager.cooldown_policy
    try:
        selection = pool._select_managers(
            keep=("gem",),
            drop_not_found=False,
            cooldown=timedelta(days=7),
            cooldown_policy=CooldownPolicy.enforce,
        )
        assert [m.cooldown_policy for m in selection] == [CooldownPolicy.enforce]

        manager.cooldown_policy = CooldownPolicy.best_effort
        pool.overridden_fields.setdefault("gem", set()).add("cooldown_policy")
        try:
            selection = pool._select_managers(
                keep=("gem",),
                drop_not_found=False,
                cooldown=timedelta(days=7),
                cooldown_policy=CooldownPolicy.enforce,
            )
            assert [m.cooldown_policy for m in selection] == [
                CooldownPolicy.best_effort,
            ]
        finally:
            pool.overridden_fields["gem"].discard("cooldown_policy")
    finally:
        manager.cooldown_policy = original


class _RecordingManager:
    """Stand-in whose `available` probe records the thread it ran on.

    Carries the four attributes {func}`probe_signature` reads. `probe` varies them
    per instance by default, so each stand-in lands on a lane of its own; passing
    the same `probe` to several puts them on a shared lane instead.
    """

    cli_search_path: tuple[str, ...] = ()
    version_cli = None
    version_cli_options: tuple[str, ...] = ("--version",)
    run_cache: dict | None = None

    _counter = itertools.count()

    def __init__(self, log: list, probe: str | None = None) -> None:
        self._log = log
        self.cli_names = (probe or f"fake-cli-{next(self._counter)}",)
        self.cache_seen: dict | None = None
        self.thread_seen: threading.Thread | None = None

    @property
    def available(self) -> bool:
        self._log.append(threading.current_thread())
        # The cache is installed for the round only, so snapshot it while probing.
        self.cache_seen = self.run_cache
        self.thread_seen = threading.current_thread()
        return True


def _jobs_context(jobs: int, verbosity: str = "INFO") -> click.Context:
    ctx = click.Context(click.Command("mpm"))
    ctx.meta[JOBS] = jobs
    ctx.meta[VERBOSITY_LEVEL] = LogLevel[verbosity]
    return ctx


def test_warm_availability_skips_without_context():
    """No active CLI context: leave probing to the lazy, sequential filter loop."""
    accessed: list = []
    managers = [_RecordingManager(accessed), _RecordingManager(accessed)]
    warm_availability(managers)  # type: ignore[arg-type]
    assert accessed == []


@pytest.mark.parametrize(
    ("jobs", "verbosity", "count"),
    (
        (1, "INFO", 4),  # --jobs 1 leaves probing to the sequential loop.
        (4, "DEBUG", 4),  # DEBUG keeps the interleaved probe logs readable.
        (4, "INFO", 1),  # A single candidate has nothing to parallelize.
    ),
)
def test_warm_availability_skips_when_not_concurrent(jobs, verbosity, count):
    accessed: list = []
    managers = [_RecordingManager(accessed) for _ in range(count)]
    with _jobs_context(jobs, verbosity):
        warm_availability(managers)  # type: ignore[arg-type]
    assert accessed == []


def test_warm_availability_probes_concurrently():
    """With --jobs > 1 and several candidates, probes run off the main thread."""
    threads: list = []
    managers = [_RecordingManager(threads) for _ in range(4)]
    with _jobs_context(jobs=4):
        warm_availability(managers)  # type: ignore[arg-type]
    assert len(threads) == 4
    assert all(thread is not threading.main_thread() for thread in threads)


def test_merge_into_probe_lanes_groups_by_signature():
    """Managers whose probe may resolve to the same command share a lane."""
    accessed: list = []
    twins = [_RecordingManager(accessed, probe="shared-cli") for _ in range(3)]
    loners = [_RecordingManager(accessed) for _ in range(2)]

    lanes = merge_into_probe_lanes([*twins, *loners])  # type: ignore[list-item]

    assert [len(lane) for lane in lanes] == [3, 1, 1]
    assert lanes[0] == tuple(twins)


def test_merge_into_probe_lanes_partitions_the_whole_pool():
    """Every manager lands on exactly one lane, whatever the pool grows to."""
    lanes = merge_into_probe_lanes(pool.values())
    laned = [manager for lane in lanes for manager in lane]
    assert len(laned) == len(pool)
    assert {manager.id for manager in laned} == set(pool.all_manager_ids)


def test_warm_availability_shares_one_cache_within_a_lane():
    """A lane's managers probe against one shared `run_cache`, then get their own
    value back: that dict is what collapses `brew` and `cask` both running
    `brew --version` into a single subprocess."""
    accessed: list = []
    twins = [_RecordingManager(accessed, probe="shared-cli") for _ in range(2)]
    loner = _RecordingManager(accessed)
    sentinel: dict = {}
    twins[1].run_cache = sentinel

    with _jobs_context(jobs=4):
        warm_availability([*twins, loner])  # type: ignore[list-item]

    assert twins[0].cache_seen is twins[1].cache_seen is not None
    # A lane of one gets no cache at all: there is no peer to share with.
    assert loner.cache_seen is None
    # A lane runs on a single worker, which is what makes the shared dict safe.
    assert twins[0].thread_seen is twins[1].thread_seen

    # Pre-existing values are restored rather than blanked.
    assert twins[0].run_cache is None
    assert twins[1].run_cache is sentinel
