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
import threading
from importlib import import_module
from pathlib import Path

import click
import pytest
from click_extra.context import JOBS, VERBOSITY

import meta_package_manager
from meta_package_manager.cli import mpm
from meta_package_manager.manager import PackageManager
from meta_package_manager.pool import manager_classes, pool, warm_availability

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
    assert len(manager_classes) == 54
    assert len(pool) == 54
    assert len(pool) == len(pool.all_manager_ids)
    assert pool.all_manager_ids == tuple(sorted(set(pool)))


def test_cached_pool():
    assert pool == pool  # noqa: PLR0124
    assert pool is pool  # noqa: PLR0124


@maintained_manager_ids
def test_maintained_managers(manager_id):
    assert pool[manager_id].deprecated is False


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


def test_extra_option_allowlist():
    assert pool.ALLOWED_EXTRA_OPTION.issubset(opt.name for opt in mpm.params)


selection_cases = {
    # Selection-logic cases pass ``drop_not_found=False`` so they test only
    # how ``keep``/``drop`` plumbing handles ordering, deduplication and
    # collection types, without depending on whether the named managers
    # have a real binary on PATH.  Hermetic builders (Guix, Nixpkgs, etc.)
    # otherwise see these cases return empty tuples because ``uv`` and
    # ``gem`` are not installed.
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
        tuple(
            mid
            for mid in pool.all_manager_ids
            if pool[mid].supported and pool[mid].available and mid != "uv"
        ),
    ),
    "duplicate_exclusions": (
        {"drop": ("uv", "uv")},
        tuple(
            mid
            for mid in pool.all_manager_ids
            if pool[mid].supported and pool[mid].available and mid != "uv"
        ),
    ),
    "multiple_exclusions": (
        {"drop": ("uv", "gem")},
        tuple(
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
        tuple(
            mid
            for mid in pool.all_manager_ids
            if pool[mid].supported and pool[mid].available
        ),
    ),
    "explicit_default_selection": (
        {"keep": None, "drop": None},
        tuple(
            mid
            for mid in pool.all_manager_ids
            if pool[mid].supported and pool[mid].available
        ),
    ),
    "keep_deprecated": (
        {"keep_deprecated": True},
        tuple(mid for mid in pool.all_manager_ids if pool[mid].available),
    ),
    "drop_deprecated": (
        {"keep_deprecated": False},
        tuple(
            mid
            for mid in pool.all_manager_ids
            if not pool[mid].deprecated and pool[mid].supported and pool[mid].available
        ),
    ),
    "keep_unsupported": (
        {"keep_unsupported": True},
        tuple(mid for mid in pool.all_manager_ids if pool[mid].available),
    ),
    "drop_unsupported": (
        {"keep_unsupported": False},
        tuple(
            mid
            for mid in pool.all_manager_ids
            if pool[mid].supported and pool[mid].available
        ),
    ),
    "drop_not_found": (
        {"drop_not_found": True},
        tuple(
            mid
            for mid in pool.all_manager_ids
            if not pool[mid].deprecated and pool[mid].supported and pool[mid].available
        ),
    ),
    "keep_not_found": (
        {"drop_not_found": False},
        tuple(
            mid
            for mid in pool.all_manager_ids
            if not pool[mid].deprecated and pool[mid].supported
        ),
    ),
}


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    (
        pytest.param(kwargs, expected, id=test_id)
        for test_id, (kwargs, expected) in selection_cases.items()
    ),
)
def test_select_managers(kwargs, expected):
    """We use tuple everywhere so we can check that select_managers() conserve the
    original order."""
    selection = pool._select_managers(**kwargs)
    assert tuple(m.id for m in selection) == expected


class _RecordingManager:
    """Stand-in whose ``available`` probe records the thread it ran on."""

    def __init__(self, log: list) -> None:
        self._log = log

    @property
    def available(self) -> bool:
        self._log.append(threading.current_thread())
        return True


def _jobs_context(jobs: int, verbosity: str = "INFO") -> click.Context:
    ctx = click.Context(click.Command("mpm"))
    ctx.meta[JOBS] = jobs
    ctx.meta[VERBOSITY] = verbosity
    return ctx


def test_warm_availability_skips_without_context():
    """No active CLI context: leave probing to the lazy, sequential filter loop."""
    accessed: list = []
    warm_availability([_RecordingManager(accessed), _RecordingManager(accessed)])
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
        warm_availability(managers)
    assert accessed == []


def test_warm_availability_probes_concurrently():
    """With --jobs > 1 and several candidates, probes run off the main thread."""
    threads: list = []
    managers = [_RecordingManager(threads) for _ in range(4)]
    with _jobs_context(jobs=4):
        warm_availability(managers)
    assert len(threads) == 4
    assert all(thread is not threading.main_thread() for thread in threads)
