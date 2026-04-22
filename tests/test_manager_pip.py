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
"""Pip-specific tests for the self-dependency filter."""

from __future__ import annotations

import importlib.metadata
from unittest.mock import MagicMock, patch

import pytest

from meta_package_manager.managers.pip import Pip


def _make_dist(requires=None, installer="pip"):
    """Build a mock distribution with the given requires and INSTALLER tag."""
    dist = MagicMock()
    dist.requires = requires
    dist.read_text = lambda name: f"{installer}\n" if name == "INSTALLER" else None
    return dist


PATCH_TARGET = "meta_package_manager.managers.pip.importlib.metadata.distribution"


def test_own_deps_empty_when_not_installed():
    """Return empty set when the mpm distribution is missing."""
    with patch(
        PATCH_TARGET,
        side_effect=importlib.metadata.PackageNotFoundError("x"),
    ):
        assert Pip._own_dependency_names() == frozenset()


@pytest.mark.parametrize("installer", ["uv", "poetry", "pdm", ""])
def test_own_deps_empty_for_non_pip_installer(installer):
    """Skip the tree walk for installers that preserve Requires-Dist metadata."""
    with patch(PATCH_TARGET, return_value=_make_dist(installer=installer)):
        assert Pip._own_dependency_names() == frozenset()


def test_own_deps_walks_tree_for_pip_installer():
    """Walk the dependency tree when the installer is pip."""
    dists = {
        "meta-package-manager": _make_dist(
            requires=["click-extra>=7.11", "cyclonedx-python-lib[validation]>=11.2"],
        ),
        "click-extra": _make_dist(requires=["click>=8"]),
        "cyclonedx-python-lib": _make_dist(requires=["lxml ; extra == 'validation'"]),
        "click": _make_dist(requires=None),
        "lxml": _make_dist(requires=None),
    }

    def fake_distribution(name):
        key = name.lower().replace("_", "-")
        if key in dists:
            return dists[key]
        raise importlib.metadata.PackageNotFoundError(name)

    with patch(PATCH_TARGET, side_effect=fake_distribution):
        result = Pip._own_dependency_names()

    assert "lxml" in result
    assert "click-extra" in result
    assert "click" in result
    assert "cyclonedx-python-lib" in result


def test_own_deps_excludes_mpm_itself():
    """meta-package-manager must not appear in the returned set."""
    dists = {
        "meta-package-manager": _make_dist(requires=["some-dep>=1"]),
        "some-dep": _make_dist(requires=None),
    }

    def fake_distribution(name):
        key = name.lower().replace("_", "-")
        if key in dists:
            return dists[key]
        raise importlib.metadata.PackageNotFoundError(name)

    with patch(PATCH_TARGET, side_effect=fake_distribution):
        result = Pip._own_dependency_names()

    assert "meta-package-manager" not in result
    assert "some-dep" in result


def test_own_deps_normalizes_names():
    """Package names are PEP 503 normalized: lowercase, hyphens only."""
    dists = {
        "meta-package-manager": _make_dist(
            requires=["My_Fancy.Lib>=1"],
        ),
        "my-fancy-lib": _make_dist(requires=None),
    }

    def fake_distribution(name):
        key = name.lower().replace("_", "-").replace(".", "-")
        if key in dists:
            return dists[key]
        raise importlib.metadata.PackageNotFoundError(name)

    with patch(PATCH_TARGET, side_effect=fake_distribution):
        result = Pip._own_dependency_names()

    # The normalized form should be in the set, not the original.
    assert "my-fancy-lib" in result
    assert "My_Fancy.Lib" not in result


def test_own_deps_handles_missing_transitive_dep():
    """Gracefully skip dependencies whose distribution is not installed."""
    dists = {
        "meta-package-manager": _make_dist(
            requires=["installed-dep>=1", "missing-dep>=2"],
        ),
        "installed-dep": _make_dist(requires=None),
    }

    def fake_distribution(name):
        key = name.lower().replace("_", "-")
        if key in dists:
            return dists[key]
        raise importlib.metadata.PackageNotFoundError(name)

    with patch(PATCH_TARGET, side_effect=fake_distribution):
        result = Pip._own_dependency_names()

    assert "installed-dep" in result
    # missing-dep still appears in the set (it was queued and added to
    # seen before the lookup failed), which is the correct behavior: it
    # should be filtered from outdated results regardless.
    assert "missing-dep" in result
