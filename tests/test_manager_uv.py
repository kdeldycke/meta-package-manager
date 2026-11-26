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
"""`uv`-specific behaviors: the launched-by-uv cache guard and the PEP 668 guard.

A parent `uv run` (or `uvx`) process keeps a lock on the uv cache for as long
as its child lives, so an `mpm` launched through it must not attempt ``uv cache
clean`: the command would wait on its own ancestor for `UV_LOCK_TIMEOUT`` and
fail. `uv` marks its children with the `UV` environment variable.

Outside a virtual environment, `uv pip` reads a system Python. When that Python
is externally managed, the `uv` manager reports as unavailable.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from meta_package_manager.manager import PackageManager
from meta_package_manager.managers.uv import UV, UVX
from meta_package_manager.pool import pool

PATCH_RUN = "meta_package_manager.managers.uv.subprocess.run"

UV_PATH = Path("/usr/bin/uv")
PYTHON_PATH = Path("/usr/bin/python")


def _completed(stdout, returncode=0):
    """Mock a `subprocess.run` result carrying the given stdout and exit code."""
    result = MagicMock()
    result.stdout = stdout
    result.returncode = returncode
    return result


@pytest.fixture
def uv_manager(monkeypatch):
    """A new `uv` manager that meets every base condition of availability."""
    monkeypatch.setattr(
        PackageManager, "unavailable_reason", property(lambda self: None)
    )
    manager = UV()
    monkeypatch.setattr(manager, "cli_path", UV_PATH, raising=False)
    return manager


@pytest.mark.parametrize(
    ("probe_stdout", "expected"),
    (
        pytest.param(
            "1\n",
            f"uv pip targets {PYTHON_PATH}, an externally managed Python: the system "
            "package manager owns its packages",
            id="externally-managed",
        ),
        pytest.param("0\n", None, id="not-externally-managed"),
        pytest.param("", None, id="empty-answer"),
    ),
)
def test_unavailable_when_uv_pip_targets_externally_managed_python(
    uv_manager, probe_stdout, expected
):
    """The interpreter `uv python find` names runs the PEP 668 probe."""
    answers = (_completed(f"{PYTHON_PATH}\n"), _completed(probe_stdout))
    with patch(PATCH_RUN, side_effect=answers) as run:
        assert uv_manager.unavailable_reason == expected

    find, probe = (call.args[0] for call in run.call_args_list)
    assert find == (
        str(UV_PATH),
        "--color",
        "never",
        "--no-progress",
        "python",
        "find",
        "--no-project",
        "default",
    )
    assert probe[:2] == (str(PYTHON_PATH), "-c")
    assert "EXTERNALLY-MANAGED" in probe[2]


@pytest.mark.parametrize(
    "answers",
    (
        pytest.param((_completed("", returncode=2),), id="no-interpreter-found"),
        pytest.param(
            (_completed(f"{PYTHON_PATH}\n{PYTHON_PATH}\n"),), id="two-answer-lines"
        ),
        pytest.param((OSError("no uv"),), id="uv-cannot-run"),
        pytest.param((subprocess.TimeoutExpired("uv", 1),), id="uv-timeout"),
        pytest.param(
            (_completed(f"{PYTHON_PATH}\n"), OSError("not a python")),
            id="python-cannot-run",
        ),
        pytest.param(
            (_completed(f"{PYTHON_PATH}\n"), subprocess.TimeoutExpired("python", 1)),
            id="python-timeout",
        ),
    ),
)
def test_failed_probe_keeps_uv_available(uv_manager, answers):
    """A probe that cannot answer must not hide the manager."""
    with patch(PATCH_RUN, side_effect=answers):
        assert uv_manager.unavailable_reason is None


def test_base_reason_wins_over_the_python_probe(monkeypatch):
    """A host failing a base condition reports it, and runs no probe."""
    monkeypatch.setattr(
        PackageManager,
        "unavailable_reason",
        property(lambda self: "not supported on macOS"),
    )
    with patch(PATCH_RUN) as run:
        assert UV().unavailable_reason == "not supported on macOS"
    run.assert_not_called()


def test_uvx_runs_no_python_probe(monkeypatch):
    """`uv tool` keeps each tool in its own virtual environment: no probe."""
    monkeypatch.setattr(
        PackageManager, "unavailable_reason", property(lambda self: None)
    )
    with patch(PATCH_RUN) as run:
        assert UVX().unavailable_reason is None
    run.assert_not_called()


@pytest.fixture
def capture_uv_run_cli(capture_run_cli):
    """Record the `uv` manager's `run_cli` invocations instead of executing."""
    return capture_run_cli(pool["uv"])


def test_cleanup_cache_skipped_under_uv(monkeypatch, caplog, capture_uv_run_cli):
    """Launched by `uv run`, the cache commands are skipped with a warning.

    They would deadlock on the parent's cache lock until `UV_LOCK_TIMEOUT`.
    """
    monkeypatch.setenv("UV", "/fake/bin/uv")
    with caplog.at_level(logging.WARNING):
        pool["uv"].cleanup_cache()
    assert capture_uv_run_cli == []
    assert "skip cache cleanup" in caplog.text


def test_cleanup_cache_runs_outside_uv(monkeypatch, capture_uv_run_cli):
    """Outside a `uv` launcher, the cache clean and prune both run."""
    monkeypatch.delenv("UV", raising=False)
    pool["uv"].cleanup_cache()
    assert capture_uv_run_cli == [("cache", "clean"), ("cache", "prune")]
