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
"""Checks for the two orphan features and their native-command mappings.

``remove --orphans`` (scoped, :py:meth:`PackageManager.remove_orphan`) drops one
package's own orphaned dependencies; ``cleanup --orphans`` (system-wide,
:py:meth:`PackageManager.cleanup_orphan`) sweeps every orphaned package. The argv
assertions stub ``run_cli`` on the pooled manager singleton to capture command tokens
without spawning a subprocess, so they run identically on any host.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from meta_package_manager.capabilities import (
    Operations,
    cleanup_orphan_is_synthesized,
    implements,
    implements_method,
    supports_cleanup_orphan,
)
from meta_package_manager.manager import PackageManager
from meta_package_manager.pool import pool

from .conftest import _patch_pool_with
from .fake_manager import FakeManager


def _capture_run_cli(monkeypatch, manager_id, call):
    """Invoke ``call(manager)`` with ``run_cli`` and ``sibling_cli`` stubbed.

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
    call(manager)
    return [token for args in calls for token in args]


# remove --orphans: scoped cascade verbs (one package's own orphaned dependencies).


@pytest.mark.parametrize(
    ("manager_id", "cascade_token"),
    (
        ("apt", "--auto-remove"),
        ("dnf", "autoremove"),
        ("dnf5", "autoremove"),
        ("pacman", "--recursive"),
        ("xbps", "--recursive"),
        ("yum", "autoremove"),
        ("zypper", "--clean-deps"),
    ),
)
def test_remove_orphan_uses_native_cascade(monkeypatch, manager_id, cascade_token):
    """``remove --orphans`` maps to each manager's native remove-plus-orphans verb."""
    tokens = _capture_run_cli(
        monkeypatch, manager_id, lambda m: m.remove_orphan("firefox")
    )
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
    tokens = _capture_run_cli(monkeypatch, manager_id, lambda m: m.remove("firefox"))
    assert cascade_token not in tokens
    assert "firefox" in tokens


@pytest.mark.parametrize(
    "manager_id",
    ("brew", "cask", "flatpak", "npm", "pip", "pkg", "snap"),
)
def test_remove_orphan_unsupported_raises_not_implemented(manager_id):
    """A manager with no scoped cascade leaves ``remove_orphan`` unimplemented, so the
    CLI action catches the ``NotImplementedError`` and falls back to a plain removal."""
    with pytest.raises(NotImplementedError):
        pool[manager_id].remove_orphan("firefox")


# cleanup --orphans: system-wide orphan sweeps (every orphaned package).


@pytest.mark.parametrize(
    ("manager_id", "sweep_token"),
    (
        ("apt", "autoremove"),
        ("brew", "autoremove"),
        ("cask", "autoremove"),
        ("dnf", "autoremove"),
        ("dnf5", "autoremove"),
        ("flatpak", "--unused"),
        ("pkg", "autoremove"),
        ("xbps", "--remove-orphans"),
        ("yum", "autoremove"),
    ),
)
def test_cleanup_orphan_uses_native_sweep(monkeypatch, manager_id, sweep_token):
    """``cleanup --orphans`` maps to each manager's system-wide orphan sweep."""
    tokens = _capture_run_cli(monkeypatch, manager_id, lambda m: m.cleanup_orphan())
    assert sweep_token in tokens


@pytest.mark.parametrize(
    ("manager_id", "sweep_token", "cache_token"),
    (
        ("apt", "autoremove", "clean"),
        ("brew", "autoremove", "cleanup"),
        ("dnf", "autoremove", "clean"),
        ("pkg", "autoremove", "clean"),
    ),
)
def test_cleanup_still_runs_orphan_sweep(
    monkeypatch, manager_id, sweep_token, cache_token
):
    """Plain ``cleanup`` keeps doing both the orphan sweep and the cache pruning: the
    sweep step now routes through ``cleanup_orphan`` but the behavior is unchanged."""
    tokens = _capture_run_cli(monkeypatch, manager_id, lambda m: m.cleanup())
    assert sweep_token in tokens
    assert cache_token in tokens


@pytest.mark.parametrize("manager_id", ("npm", "pip", "snap"))
def test_cleanup_orphan_unsupported_raises_not_implemented(manager_id):
    """A manager with neither a native sweep nor an ``orphans`` query propagates
    ``NotImplementedError`` from the base sweep, so ``cleanup --orphans`` skips it."""
    with pytest.raises(NotImplementedError):
        pool[manager_id].cleanup_orphan()


@pytest.mark.parametrize(
    ("manager_id", "synthesized", "supported"),
    (
        # Native sweep verb: supported, nothing to synthesize.
        ("apt", False, True),
        ("brew", False, True),
        ("cask", False, True),
        ("dnf", False, True),
        ("flatpak", False, True),
        ("pkg", False, True),
        ("xbps", False, True),
        # No native verb, but orphans + remove: mpm synthesizes the sweep.
        ("pacaur", True, True),
        ("pacman", True, True),
        ("paru", True, True),
        ("yay", True, True),
        ("zypper", True, True),
        # No orphan support at all.
        ("npm", False, False),
        ("pip", False, False),
        ("snap", False, False),
    ),
)
def test_cleanup_orphan_capability_matrix(manager_id, synthesized, supported):
    """The synthesized sweep covers exactly the managers with an orphan listing and
    per-package removal but no native sweep verb, mirroring ``upgrade --all``."""
    manager = pool[manager_id]
    assert cleanup_orphan_is_synthesized(manager) is synthesized
    assert supports_cleanup_orphan(manager) is supported


def test_synthesized_sweep_fixpoint(monkeypatch):
    """The synthesized sweep re-queries between rounds and stops when the listing
    settles: removing an orphan can orphan its own dependencies."""
    manager = pool["pacman"]
    rounds = iter((
        "liborphan 1.0-1\nlibleaf 2.0-1",
        "libnewly-orphaned 0.5-1",
        "",
    ))
    removed = []

    def fake_run_cli(*args, **kwargs):
        if "--query" in args:
            return next(rounds)
        removed.append(args)
        return ""

    monkeypatch.setattr(manager, "run_cli", fake_run_cli)
    manager.cleanup_orphan()
    assert removed == [
        ("--remove", "--recursive", "liborphan"),
        ("--remove", "--recursive", "libleaf"),
        ("--remove", "--recursive", "libnewly-orphaned"),
    ]


def test_synthesized_sweep_stops_without_progress(monkeypatch):
    """A removal that keeps failing cannot spin the loop: two identical consecutive
    listings end the sweep."""
    manager = pool["pacman"]
    removed = []

    def fake_run_cli(*args, **kwargs):
        if "--query" in args:
            return "libstuck 1.0-1"
        removed.append(args)
        return ""

    monkeypatch.setattr(manager, "run_cli", fake_run_cli)
    manager.cleanup_orphan()
    assert removed == [("--remove", "--recursive", "libstuck")]


# orphans query: native read-only listings parsed into packages.


_APT_ORPHANS_OUTPUT = """\
NOTE: This is only a simulation!
      apt needs root privileges for real execution.
Reading package lists...
The following packages will be REMOVED:
  libx11-dev libxcb1-dev
0 upgraded, 0 newly installed, 2 to remove and 0 not upgraded.
Remv libx11-dev [2:1.8.7-1]
Remv libxcb1-dev [1.15-1]
"""

_BREW_ORPHANS_OUTPUT = """\
==> Would autoremove 3 unneeded formulae:
libpng
little-cms2
openjpeg
Warning: some warning to ignore
"""

_DNF_ORPHANS_OUTPUT = """\
libfoo-1.0.2-3.el9.x86_64
python3-extra-0:3.9.18-3.el9.noarch
"""

_PACMAN_ORPHANS_OUTPUT = """\
gtest 1.14.0-1
libwlroots 0.16.2-2
"""

_PKG_ORPHANS_OUTPUT = """\
Checking integrity... done (0 conflicting)
Deinstallation has been requested for the following 2 packages:

Installed packages to be REMOVED:
\tlibiconv: 1.17
\tpcre: 8.45_3

Number of packages to be removed: 2
"""

_XBPS_ORPHANS_OUTPUT = """\
libglvnd-1.7.0_1
orc-0.4.34_1
"""

_ZYPPER_ORPHANS_OUTPUT = """\
Loading repository data...
Reading installed packages...
S  | Repository | Name    | Version   | Arch
---+------------+---------+-----------+-------
i  | @System    | libfoo  | 1.2.3-1.1 | x86_64
i+ | openSUSE   | libbar  | 0.9-2.4   | noarch
"""


@pytest.mark.parametrize(
    ("manager_id", "output", "expected"),
    (
        (
            "apt",
            _APT_ORPHANS_OUTPUT,
            {("libx11-dev", "2:1.8.7-1"), ("libxcb1-dev", "1.15-1")},
        ),
        (
            "brew",
            _BREW_ORPHANS_OUTPUT,
            {("libpng", None), ("little-cms2", None), ("openjpeg", None)},
        ),
        (
            "dnf",
            _DNF_ORPHANS_OUTPUT,
            {("libfoo", "1.0.2-3.el9"), ("python3-extra", "3.9.18-3.el9")},
        ),
        (
            "pacman",
            _PACMAN_ORPHANS_OUTPUT,
            {("gtest", "1.14.0-1"), ("libwlroots", "0.16.2-2")},
        ),
        (
            "pkg",
            _PKG_ORPHANS_OUTPUT,
            {("libiconv", "1.17"), ("pcre", "8.45_3")},
        ),
        (
            "xbps",
            _XBPS_ORPHANS_OUTPUT,
            {("libglvnd", "1.7.0_1"), ("orc", "0.4.34_1")},
        ),
        (
            "zypper",
            _ZYPPER_ORPHANS_OUTPUT,
            {("libfoo", "1.2.3-1.1"), ("libbar", "0.9-2.4")},
        ),
    ),
)
def test_orphans_parsing(monkeypatch, manager_id, output, expected):
    """Each manager's ``orphans`` query parses its native listing into packages.

    The canned outputs mirror the ``shell-session`` samples of the ``orphans``
    docstrings, so the documented format and the tested format cannot drift apart.
    """
    manager = pool[manager_id]
    monkeypatch.setattr(manager, "run_cli", lambda *args, **kwargs: output)
    monkeypatch.setattr(
        manager,
        "sibling_cli",
        lambda name, **kwargs: Path("/fake/bin") / name,
    )
    packages = {
        (
            package.id,
            str(package.installed_version) if package.installed_version else None,
        )
        for package in manager.orphans
    }
    assert packages == expected


@pytest.mark.parametrize("manager_id", ("cask", "npm", "pip", "snap"))
def test_orphans_query_unsupported(manager_id):
    """Managers without a native read-only orphan listing (including cask: casks are
    never installed as dependencies) do not advertise the ``orphans`` operation."""
    assert implements(pool[manager_id], Operations.orphans) is False


@pytest.mark.parametrize(
    "manager_id",
    ("apt", "brew", "dnf", "dnf5", "pacman", "pkg", "xbps", "yum", "zypper"),
)
def test_orphans_query_supported(manager_id):
    assert implements(pool[manager_id], Operations.orphans) is True


# Capability introspection shared by the CLI selection and the documentation.


def test_implements_method_introspection():
    """``implements_method`` reports overrides of the base ``NotImplementedError``
    stubs, the same MRO walk the CLI and the docs generator rely on."""
    assert implements_method(pool["apt"], "remove_orphan") is True
    assert implements_method(pool["apt"], "cleanup_orphan") is True
    assert implements_method(pool["pacman"], "remove_orphan") is True
    assert implements_method(pool["pacman"], "cleanup_orphan") is False
    assert implements_method(pool["brew"], "remove_orphan") is False
    assert implements_method(pool["brew"], "cleanup_orphan") is True
    # Inherited overrides count (dnf5 and yum inherit from dnf).
    assert implements_method(pool["dnf5"], "remove_orphan") is True


def test_base_orphan_operations_not_implemented():
    """Both operations are optional, exactly like ``remove`` and ``cleanup``."""
    with pytest.raises(NotImplementedError):
        PackageManager().remove_orphan("firefox")
    with pytest.raises(NotImplementedError):
        PackageManager().cleanup_orphan()


# CLI plumbing, driven through deterministic fakes.


class RemovableFakeManager(FakeManager):
    """Fake manager that removes packages but has no scoped orphan-cascade verb.

    Exercises the ``remove --orphans`` fallback: ``remove_orphan`` stays unimplemented
    (base ``NotImplementedError``) while ``remove`` succeeds, so the CLI must catch the
    former and fall back to the latter.
    """

    def remove(self, package_id: str) -> str:
        return f"Removed {package_id}."


class CleanupFakeManager(FakeManager):
    """Fake manager that supports plain cleanup but no system-wide orphan sweep."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []

    def cleanup(self) -> None:
        self.calls.append("cleanup")


class OrphanCleanupFakeManager(CleanupFakeManager):
    """Fake manager that additionally supports the system-wide orphan sweep."""

    def cleanup_orphan(self) -> None:
        self.calls.append("cleanup_orphan")


class SweepSynthesizingFakeManager(CleanupFakeManager):
    """Fake manager with cleanup, an orphan listing (inherited) and removal, but no
    native sweep verb: ``cleanup --orphans`` must go through the synthesized base
    sweep, never the full ``cleanup``."""

    def remove(self, package_id: str) -> str:
        self.calls.append(f"remove:{package_id}")
        return ""


@pytest.fixture
def removable_fake_pool(monkeypatch):
    fake = _patch_pool_with(monkeypatch, RemovableFakeManager())
    # _dispatch_sourced_operation resolves each source manager via pool.get(id), which
    # reads pool.register. _patch_pool_with only stubs select_managers, so register the
    # fake as well for the per-package dispatch to find it.
    monkeypatch.setitem(pool.register, fake.id, fake)
    return fake


def test_remove_orphans_falls_back_to_plain_removal(invoke, removable_fake_pool):
    """``remove --orphans`` on a manager without a cascade verb removes the package
    only, narrating the skip at ``INFO`` and still exiting cleanly."""
    result = invoke("--verbosity", "INFO", "remove", "--orphans", "fake-pkg-alpha")
    assert result.exit_code == 0
    assert "Does not implement orphan removal, removing the package only." in (
        result.stderr
    )


def test_cleanup_orphans_runs_only_the_sweep(invoke, monkeypatch):
    """``cleanup --orphans`` runs ``cleanup_orphan``, not the full ``cleanup``."""
    fake = _patch_pool_with(monkeypatch, OrphanCleanupFakeManager())
    result = invoke("cleanup", "--orphans")
    assert result.exit_code == 0
    assert fake.calls == ["cleanup_orphan"]


def test_cleanup_without_orphans_runs_full_cleanup(invoke, monkeypatch):
    """Plain ``cleanup`` runs the full ``cleanup``, not the narrowed sweep."""
    fake = _patch_pool_with(monkeypatch, OrphanCleanupFakeManager())
    result = invoke("cleanup")
    assert result.exit_code == 0
    assert fake.calls == ["cleanup"]


def test_cleanup_orphans_skips_manager_without_sweep(invoke, monkeypatch):
    """A cleanup-capable manager with no orphan sweep at all (an orphan listing but
    no removal) is skipped by ``--orphans``, not fully cleaned up."""
    fake = _patch_pool_with(monkeypatch, CleanupFakeManager())
    result = invoke("cleanup", "--orphans")
    assert result.exit_code == 0
    assert fake.calls == []


def test_cleanup_orphans_runs_synthesized_sweep(invoke, monkeypatch):
    """``cleanup --orphans`` on a manager without a native sweep verb synthesizes it:
    the listed orphans are removed one by one, and the full ``cleanup`` never runs."""
    fake = _patch_pool_with(monkeypatch, SweepSynthesizingFakeManager())
    result = invoke("cleanup", "--orphans")
    assert result.exit_code == 0
    assert fake.calls == ["remove:fake-orphan-alpha"]
