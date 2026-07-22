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
"""``uv``-specific behaviors, starting with the launched-by-uv cache guard.

A parent ``uv run`` (or ``uvx``) process keeps a lock on the uv cache for as long
as its child lives, so an ``mpm`` launched through it must not attempt ``uv cache
clean``: the command would wait on its own ancestor for ``UV_LOCK_TIMEOUT`` and
fail. ``uv`` marks its children with the ``UV`` environment variable.
"""

from __future__ import annotations

import logging

import pytest

from meta_package_manager.pool import pool


@pytest.fixture
def capture_uv_run_cli(monkeypatch):
    """Record the ``uv`` manager's ``run_cli`` invocations instead of executing."""
    manager = pool["uv"]
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        manager,
        "run_cli",
        lambda *args, **kwargs: calls.append(args) or "",
    )
    return calls


def test_cleanup_cache_skipped_under_uv(monkeypatch, caplog, capture_uv_run_cli):
    """Launched by ``uv run``, the cache commands are skipped with a warning: they
    would deadlock on the parent's cache lock until ``UV_LOCK_TIMEOUT``."""
    monkeypatch.setenv("UV", "/fake/bin/uv")
    with caplog.at_level(logging.WARNING):
        pool["uv"].cleanup_cache()
    assert capture_uv_run_cli == []
    assert "skip cache cleanup" in caplog.text


def test_cleanup_cache_runs_outside_uv(monkeypatch, capture_uv_run_cli):
    """Outside a ``uv`` launcher, the cache clean and prune both run."""
    monkeypatch.delenv("UV", raising=False)
    pool["uv"].cleanup_cache()
    assert capture_uv_run_cli == [("cache", "clean"), ("cache", "prune")]
