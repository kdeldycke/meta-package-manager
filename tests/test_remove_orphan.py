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
"""Checks for ``remove --orphans`` and its native-cascade mapping.

The argv assertions stub ``run_cli`` on the pooled manager singleton to capture the
command tokens without spawning a subprocess, so they run identically on any host,
regardless of which package managers are actually installed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from meta_package_manager.manager import PackageManager
from meta_package_manager.pool import pool

from .conftest import _patch_pool_with
from .fake_manager import FakeManager


def _capture_run_cli(monkeypatch, manager_id, method, package_id):
    """Run ``manager.<method>(package_id)`` with ``run_cli`` and ``sibling_cli`` stubbed.

    ``run_cli`` records the positional argv of every invocation instead of executing
    it, and ``sibling_cli`` is neutralized because its ``same_dir`` resolution asserts
    on a ``cli_path`` that is absent on a host lacking the manager (xbps). Returns the
    flat list of every captured token across all invocations.
    """
    manager = pool[manager_id]
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        manager,
        "run_cli",
        lambda *args, **kwargs: calls.append(args) or "",
    )
    monkeypatch.setattr(
        manager,
        "sibling_cli",
        lambda name, **kwargs: Path("/fake/bin") / name,
    )
    getattr(manager, method)(package_id)
    return [token for args in calls for token in args]


@pytest.mark.parametrize(
    ("manager_id", "cascade_token"),
    (
        ("apt", "--auto-remove"),
        ("dnf", "autoremove"),
        ("dnf5", "autoremove"),
        ("pacman", "--recursive"),
        ("pkg", "autoremove"),
        ("xbps", "--recursive"),
        ("yum", "autoremove"),
        ("zypper", "--clean-deps"),
    ),
)
def test_remove_orphan_uses_native_cascade(monkeypatch, manager_id, cascade_token):
    """``remove --orphans`` maps to each manager's native remove-plus-orphans verb."""
    tokens = _capture_run_cli(monkeypatch, manager_id, "remove_orphan", "firefox")
    assert cascade_token in tokens
    assert "firefox" in tokens


@pytest.mark.parametrize(
    ("manager_id", "cascade_token"),
    (
        ("dnf", "autoremove"),
        ("dnf5", "autoremove"),
        ("xbps", "--recursive"),
        ("yum", "autoremove"),
    ),
)
def test_plain_remove_no_longer_cascades(monkeypatch, manager_id, cascade_token):
    """Plain ``remove`` keeps orphaned dependencies: dnf and xbps used to cascade."""
    tokens = _capture_run_cli(monkeypatch, manager_id, "remove", "firefox")
    assert cascade_token not in tokens
    assert "firefox" in tokens


@pytest.mark.parametrize(
    "manager_id",
    ("brew", "cask", "flatpak", "npm", "pip", "snap"),
)
def test_remove_orphan_unsupported_raises_not_implemented(manager_id):
    """A manager with no native cascade leaves ``remove_orphan`` unimplemented, so the
    CLI action can catch the ``NotImplementedError`` and fall back to a plain removal."""
    with pytest.raises(NotImplementedError):
        pool[manager_id].remove_orphan("firefox")


class RemovableFakeManager(FakeManager):
    """Fake manager that removes packages but has no native orphan-cascade verb.

    Exercises the ``--orphans`` fallback: ``remove_orphan`` stays unimplemented (base
    ``NotImplementedError``) while ``remove`` succeeds, so the CLI must catch the former
    and fall back to the latter.
    """

    def remove(self, package_id: str) -> str:
        return f"Removed {package_id}."


@pytest.fixture
def removable_fake_pool(monkeypatch):
    fake = _patch_pool_with(monkeypatch, RemovableFakeManager())
    # _dispatch_sourced_operation resolves each source manager via pool.get(id), which
    # reads pool.register. _patch_pool_with only stubs select_managers, so register the
    # fake as well for the per-package dispatch to find it.
    monkeypatch.setitem(pool.register, fake.id, fake)
    return fake


def test_remove_orphans_falls_back_to_plain_removal(invoke, removable_fake_pool):
    """``remove --orphans`` on a manager without a cascade verb removes the package only,
    narrating the skip at ``INFO`` and still exiting cleanly."""
    result = invoke("--verbosity", "INFO", "remove", "--orphans", "fake-pkg-alpha")
    assert result.exit_code == 0
    assert "Does not implement orphan removal, removing the package only." in (
        result.stderr
    )


def test_base_remove_orphan_not_implemented():
    """The base operation is optional, exactly like ``remove`` itself."""
    with pytest.raises(NotImplementedError):
        PackageManager().remove_orphan("firefox")
