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

"""Unit tests for the concurrent operation dispatch helpers.

These exercise :func:`meta_package_manager.execution.collect_from_managers`,
:func:`meta_package_manager.execution.collect_per_package` and the
:class:`meta_package_manager.execution.OperationTrail` they share, in isolation with
lightweight stand-ins for the click context and managers, so they need no real package
managers and stay hermetic. The context is passed explicitly as ``ctx=`` (the helpers
otherwise default to :func:`click_extra.get_current_context`).
"""

from __future__ import annotations

import io
import threading
import time

import pytest
from click_extra.context import JOBS, VERBOSITY_LEVEL
from click_extra.logging import LogLevel
from click_extra.theme import KO_GLYPH, OK_GLYPH

import meta_package_manager.execution
from meta_package_manager.execution import (
    OperationTrail,
    collect_from_managers,
    collect_per_package,
)


class FakeContext:
    """Minimal stand-in exposing only the ``meta`` keys the helper reads."""

    def __init__(self, jobs: int, verbosity: str = "INFO") -> None:
        self.meta = {
            JOBS: jobs,
            VERBOSITY_LEVEL: LogLevel[verbosity],
        }


class FakeManager:
    """Minimal stand-in exposing only ``id`` and the ``progress`` gate."""

    def __init__(self, manager_id: str, progress: bool = False) -> None:
        self.id = manager_id
        self.progress = progress


class TTYStringIO(io.StringIO):
    """An in-memory text buffer that claims to be an interactive terminal."""

    def isatty(self) -> bool:
        return True


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
        "Testing",
        "Tested",
        managers,  # type: ignore[arg-type]
        _record_thread(threads, threading.Lock()),
        ctx=ctx,  # type: ignore[arg-type]
    )
    assert threads, "work was never called"
    assert all(thread is threading.main_thread() for thread in threads)


def test_runs_concurrently_off_the_main_thread():
    ctx = FakeContext(jobs=4)
    managers = [FakeManager(f"m{i}") for i in range(4)]
    threads: list = []
    collect_from_managers(
        "Testing",
        "Tested",
        managers,  # type: ignore[arg-type]
        _record_thread(threads, threading.Lock()),
        ctx=ctx,  # type: ignore[arg-type]
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

    results = collect_from_managers(
        "Testing",
        "Tested",
        managers,  # type: ignore[arg-type]
        work,
        ctx=ctx,  # type: ignore[arg-type]
    )
    assert [manager_id for manager_id, _ in results] == [f"m{i}" for i in range(8)]


def test_suppresses_per_manager_spinners_when_concurrent():
    """Concurrent mode mutes per-manager spinners (one aggregate stands in)."""
    ctx = FakeContext(jobs=4)
    managers = [FakeManager(f"m{i}", progress=True) for i in range(4)]
    collect_from_managers(
        "Testing",
        "Tested",
        managers,  # type: ignore[arg-type]
        lambda manager: (manager.id, {}),
        ctx=ctx,  # type: ignore[arg-type]
    )
    assert all(manager.progress is False for manager in managers)


def test_keeps_per_manager_spinners_when_sequential():
    """Sequential mode leaves the per-manager spinner gate untouched."""
    ctx = FakeContext(jobs=1)
    managers = [FakeManager(f"m{i}", progress=True) for i in range(3)]
    collect_from_managers(
        "Testing",
        "Tested",
        managers,  # type: ignore[arg-type]
        lambda manager: (manager.id, {}),
        ctx=ctx,  # type: ignore[arg-type]
    )
    assert all(manager.progress is True for manager in managers)


def test_empty_manager_list_returns_empty():
    ctx = FakeContext(jobs=4)
    assert (
        collect_from_managers(
            "Testing",
            "Tested",
            [],
            lambda manager: (manager.id, {}),
            ctx=ctx,  # type: ignore[arg-type]
        )
        == []
    )


def test_no_finisher_line_off_terminal(capsys):
    """Off a terminal the aggregate spinner never draws, so no finisher leaks.

    ``Spinner.ok()`` emits its line unconditionally, so the gate must keep it out
    of pipes, captured output and serialized runs.
    """
    ctx = FakeContext(jobs=4)
    managers = [FakeManager(f"m{i}", progress=True) for i in range(4)]
    collect_from_managers(
        "Searching",
        "Searched",
        managers,  # type: ignore[arg-type]
        lambda manager: (manager.id, {}),
        ctx=ctx,  # type: ignore[arg-type]
    )
    assert "Searched" not in capsys.readouterr().err


def test_finisher_line_when_spinner_shown(monkeypatch):
    """A slow batch on a terminal shows the running count, a ✓ trail and a finisher."""
    # Zero the show-delay so the spinner draws at once, and point it at a fake TTY.
    monkeypatch.setattr(meta_package_manager.execution, "SPINNER_DELAY", 0.0)
    tty = TTYStringIO()
    monkeypatch.setattr("sys.stderr", tty)

    ctx = FakeContext(jobs=4)
    managers = [FakeManager(f"m{i}", progress=True) for i in range(4)]

    def slow_work(manager):
        time.sleep(0.1)  # Outlast the zeroed delay so the spinner draws a frame.
        return manager.id, {}

    collect_from_managers(
        "Searching",
        "Searched",
        managers,  # type: ignore[arg-type]
        slow_work,
        ctx=ctx,  # type: ignore[arg-type]
    )
    output = tty.getvalue()
    # The spinner draws its seeded running count before any manager lands...
    assert "Searching 0/4 managers" in output
    # ...leaves a ✓ trail line naming every manager as it completes (no errors)...
    assert all(f"m{i}" in output for i in range(4))
    assert OK_GLYPH in output
    # ...then settles on the persistent past-tense finisher once all have.
    assert "Searched 4 managers" in output


def test_failure_trail_marks_errored_managers(monkeypatch):
    """A manager whose result carries errors gets a ✗ trail line; others get ✓."""
    monkeypatch.setattr(meta_package_manager.execution, "SPINNER_DELAY", 0.0)
    tty = TTYStringIO()
    monkeypatch.setattr("sys.stderr", tty)

    ctx = FakeContext(jobs=4)
    managers = [FakeManager(f"m{i}", progress=True) for i in range(4)]

    def work(manager):
        time.sleep(0.1)  # Outlast the zeroed delay so the spinner draws a frame.
        # A non-empty "errors" list marks a manager as failed in the trail.
        errors = ["boom"] if manager.id == "m2" else []
        return manager.id, {"errors": errors}

    collect_from_managers(
        "Searching",
        "Searched",
        managers,  # type: ignore[arg-type]
        work,
        ctx=ctx,  # type: ignore[arg-type]
    )
    output = tty.getvalue()
    assert KO_GLYPH in output  # The failure glyph, for m2.
    assert OK_GLYPH in output  # The success glyph, for the other managers.


def test_trail_includes_managers_that_finish_before_the_spinner_shows(monkeypatch):
    """Managers that complete within the show delay still get a trail line.

    Regression: the per-manager echo was gated on the live ``shown`` state, so a
    manager that finished before the spinner first drew was dropped from the trail
    (a 6-manager batch where the quick ones beat the 1s delay showed only the 3
    slow ones, above a "Checked 6 managers" finisher). Outcomes are now buffered
    and flushed once the spinner appears, so the ledger stays complete.
    """
    # A show delay the fast managers beat but the slow ones outlast (so the spinner
    # still draws and the trail surfaces at all).
    monkeypatch.setattr(meta_package_manager.execution, "SPINNER_DELAY", 0.2)
    tty = TTYStringIO()
    monkeypatch.setattr("sys.stderr", tty)

    ctx = FakeContext(jobs=6)
    managers = [FakeManager(f"m{i}", progress=True) for i in range(6)]

    def work(manager):
        # m0, m1, m2 finish before the show delay; m3, m4, m5 finish after it.
        time.sleep(0.03 if int(manager.id[1:]) < 3 else 0.4)
        return manager.id, {}

    collect_from_managers(
        "Checking",
        "Checked",
        managers,  # type: ignore[arg-type]
        work,
        ctx=ctx,  # type: ignore[arg-type]
    )
    output = tty.getvalue()
    # Every manager — fast and slow alike — appears, not just the slow three.
    assert all(f"m{i}" in output for i in range(6))
    assert "Checked 6 managers" in output


# ---------------------------------------------------------------------------
# Per-package fan-out: collect_per_package (and the dispatch engine beneath it).
# It takes flat (manager, task) pairs and groups them into per-manager lanes.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("jobs", "verbosity", "manager_count"),
    (
        (1, "INFO", 4),  # --jobs 1 forces sequential.
        (4, "DEBUG", 4),  # DEBUG forces sequential for readable logs.
        (4, "INFO", 1),  # A single manager has nothing to parallelize.
    ),
)
def test_per_package_runs_sequentially_in_main_thread(jobs, verbosity, manager_count):
    ctx = FakeContext(jobs=jobs, verbosity=verbosity)
    threads: list = []
    lock = threading.Lock()

    def make_task(manager_id):
        def task():
            with lock:
                threads.append(threading.current_thread())
            return True, f"{manager_id} ok"

        return task

    tasks = [(FakeManager(f"m{i}"), make_task(f"m{i}")) for i in range(manager_count)]
    collect_per_package("Doing", "Done", tasks, ctx=ctx)  # type: ignore[arg-type]
    assert threads, "no task was called"
    assert all(thread is threading.main_thread() for thread in threads)


def test_per_package_runs_concurrently_off_the_main_thread():
    ctx = FakeContext(jobs=4)
    threads: list = []
    lock = threading.Lock()

    def make_task(manager_id):
        def task():
            with lock:
                threads.append(threading.current_thread())
            return True, f"{manager_id} ok"

        return task

    tasks = [(FakeManager(f"m{i}"), make_task(f"m{i}")) for i in range(4)]
    collect_per_package("Doing", "Done", tasks, ctx=ctx)  # type: ignore[arg-type]
    assert len(threads) == 4
    assert all(thread is not threading.main_thread() for thread in threads)


def test_per_package_tasks_of_one_manager_share_a_thread():
    """A manager's own tasks run serially on one worker, never overlapping.

    The core safety invariant: a package manager cannot run two of its own
    invocations at once, so each lane's tasks stay on a single thread. Repeating the
    same manager instance across pairs groups its tasks into one lane.
    """
    ctx = FakeContext(jobs=4)
    threads_by_manager: dict = {}
    lock = threading.Lock()

    def make_task(manager_id):
        def task():
            time.sleep(0.01)
            with lock:
                threads_by_manager.setdefault(manager_id, []).append(
                    threading.current_thread()
                )
            return True, f"{manager_id} ok"

        return task

    managers = [FakeManager(f"m{i}") for i in range(4)]
    tasks = [(manager, make_task(manager.id)) for manager in managers for _ in range(3)]
    collect_per_package("Doing", "Done", tasks, ctx=ctx)  # type: ignore[arg-type]
    assert set(threads_by_manager) == {f"m{i}" for i in range(4)}
    for manager_id, threads in threads_by_manager.items():
        assert len(threads) == 3, manager_id
        assert len(set(threads)) == 1, f"{manager_id} tasks split across threads"


def test_per_package_empty_is_a_noop():
    ctx = FakeContext(jobs=4)
    # No tasks: returns without dispatching anything (and raises nothing).
    collect_per_package("Doing", "Done", [], ctx=ctx)  # type: ignore[arg-type]


def test_per_package_finisher_when_spinner_shown(monkeypatch):
    """A slow concurrent batch shows the running count, a ✓ trail and a finisher."""
    monkeypatch.setattr(meta_package_manager.execution, "SPINNER_DELAY", 0.0)
    tty = TTYStringIO()
    monkeypatch.setattr("sys.stderr", tty)

    ctx = FakeContext(jobs=4)

    def make_task(manager_id, k):
        def task():
            time.sleep(0.1)  # Outlast the zeroed delay so the spinner draws a frame.
            return True, f"pkg{k} done with {manager_id}"

        return task

    managers = [FakeManager(f"m{i}", progress=True) for i in range(3)]
    tasks = [(m, make_task(m.id, k)) for m in managers for k in range(2)]
    collect_per_package("Removing", "Removed", tasks, ctx=ctx)  # type: ignore[arg-type]
    output = tty.getvalue()
    assert "Removing 0/6 packages" in output  # 3 managers × 2 packages.
    assert OK_GLYPH in output
    assert "Removed 6/6 packages" in output


def test_per_package_failure_trail_marks_failed_tasks(monkeypatch):
    """A failed task gets a ✗ line; the finisher reports the success count."""
    monkeypatch.setattr(meta_package_manager.execution, "SPINNER_DELAY", 0.0)
    tty = TTYStringIO()
    monkeypatch.setattr("sys.stderr", tty)

    ctx = FakeContext(jobs=4)

    def make_task(manager_id, ok):
        def task():
            time.sleep(0.1)
            return ok, f"{manager_id} {'removed' if ok else 'failed'}"

        return task

    managers = [FakeManager(f"m{i}", progress=True) for i in range(3)]
    # m1's single task fails; the other two succeed.
    tasks = [(m, make_task(m.id, m.id != "m1")) for m in managers]
    collect_per_package("Removing", "Removed", tasks, ctx=ctx)  # type: ignore[arg-type]
    output = tty.getvalue()
    assert KO_GLYPH in output  # m1.
    assert OK_GLYPH in output  # m0 and m2.
    assert "Removed 2/3 packages" in output


def test_per_package_no_finisher_off_terminal(capsys):
    """Off a terminal nothing leaks (the trail and finisher are spinner-gated)."""
    ctx = FakeContext(jobs=4)
    managers = [FakeManager(f"m{i}", progress=True) for i in range(4)]
    tasks = [(m, lambda mid=m.id: (True, f"{mid} ok")) for m in managers]
    collect_per_package("Removing", "Removed", tasks, ctx=ctx)  # type: ignore[arg-type]
    assert "Removed" not in capsys.readouterr().err


# ---------------------------------------------------------------------------
# OperationTrail: the sequential ✓/✗ ledger (drives install's priority search
# and every sequential fallback).
# ---------------------------------------------------------------------------


def test_operation_trail_echoes_marks_and_finisher_on_tty(monkeypatch):
    """On a TTY the ledger echoes a ✓/✗ line per mark, plus a timed finisher."""
    tty = TTYStringIO()
    monkeypatch.setattr("sys.stderr", tty)
    trail = OperationTrail([FakeManager("brew", progress=True)])  # type: ignore[list-item]
    trail.mark(True, "foo installed with brew")
    trail.mark(False, "bar failed with brew")
    trail.finish(False, "Installed 1/2 packages")
    output = tty.getvalue()
    assert "foo installed with brew" in output
    assert "bar failed with brew" in output
    assert OK_GLYPH in output
    assert KO_GLYPH in output
    assert "Installed 1/2 packages" in output


def test_operation_trail_silent_off_terminal(capsys):
    """Off a terminal the sequential ledger stays silent."""
    trail = OperationTrail([FakeManager("brew", progress=True)])  # type: ignore[list-item]
    trail.mark(True, "foo installed with brew")
    trail.finish(True, "Installed 1/1 packages")
    assert capsys.readouterr().err == ""
