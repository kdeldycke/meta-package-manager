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

"""Unit tests for the concurrent read-only operation dispatch helper.

These exercise :func:`meta_package_manager.cli.collect_from_managers` in
isolation, with lightweight stand-ins for the click context and managers, so
they need no real package managers and stay hermetic.
"""

from __future__ import annotations

import threading
import time

import pytest

from meta_package_manager.cli import collect_from_managers


class FakeContext:
    """Minimal stand-in exposing only the ``meta`` keys the helper reads."""

    def __init__(self, jobs: int, verbosity: str = "INFO") -> None:
        self.meta = {
            "click_extra.jobs": jobs,
            "click_extra.verbosity": verbosity,
        }


class FakeManager:
    """Minimal stand-in exposing only ``id`` and the ``progress`` gate."""

    def __init__(self, manager_id: str, progress: bool = False) -> None:
        self.id = manager_id
        self.progress = progress


def _record_thread(threads, lock):
    """Build a ``work`` callable that records the thread each call runs on."""

    def work(manager):
        with lock:
            threads.append(threading.current_thread())
        return manager.id, {}

    return work


@pytest.mark.parametrize(
    ("jobs", "verbosity", "manager_count"),
    (
        (1, "INFO", 4),  # --jobs 1 forces sequential.
        (4, "DEBUG", 4),  # DEBUG forces sequential for readable logs.
        (4, "INFO", 1),  # A single manager has nothing to parallelize.
    ),
)
def test_runs_sequentially_in_main_thread(jobs, verbosity, manager_count):
    ctx = FakeContext(jobs=jobs, verbosity=verbosity)
    managers = [FakeManager(f"m{i}") for i in range(manager_count)]
    threads: list = []
    collect_from_managers(
        ctx, "Testing", managers, _record_thread(threads, threading.Lock())
    )
    assert threads, "work was never called"
    assert all(thread is threading.main_thread() for thread in threads)


def test_runs_concurrently_off_the_main_thread():
    ctx = FakeContext(jobs=4)
    managers = [FakeManager(f"m{i}") for i in range(4)]
    threads: list = []
    collect_from_managers(
        ctx, "Testing", managers, _record_thread(threads, threading.Lock())
    )
    assert len(threads) == 4
    assert all(thread is not threading.main_thread() for thread in threads)


def test_preserves_input_order_despite_completion_order():
    """Results follow the manager order, even when later managers finish first."""
    ctx = FakeContext(jobs=4)
    managers = [FakeManager(f"m{i}") for i in range(8)]

    def work(manager):
        index = int(manager.id[1:])
        # Earlier managers sleep longest, so completion order reverses input order.
        time.sleep(0.01 * (len(managers) - index))
        return manager.id, {"index": index}

    results = collect_from_managers(ctx, "Testing", managers, work)
    assert [manager_id for manager_id, _ in results] == [f"m{i}" for i in range(8)]


def test_suppresses_per_manager_spinners_when_concurrent():
    """Concurrent mode mutes per-manager spinners (one aggregate stands in)."""
    ctx = FakeContext(jobs=4)
    managers = [FakeManager(f"m{i}", progress=True) for i in range(4)]
    collect_from_managers(ctx, "Testing", managers, lambda manager: (manager.id, {}))
    assert all(manager.progress is False for manager in managers)


def test_keeps_per_manager_spinners_when_sequential():
    """Sequential mode leaves the per-manager spinner gate untouched."""
    ctx = FakeContext(jobs=1)
    managers = [FakeManager(f"m{i}", progress=True) for i in range(3)]
    collect_from_managers(ctx, "Testing", managers, lambda manager: (manager.id, {}))
    assert all(manager.progress is True for manager in managers)


def test_empty_manager_list_returns_empty():
    ctx = FakeContext(jobs=4)
    assert (
        collect_from_managers(ctx, "Testing", [], lambda manager: (manager.id, {}))
        == []
    )
