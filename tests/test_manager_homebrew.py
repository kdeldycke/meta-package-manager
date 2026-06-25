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
"""Homebrew-specific tests."""

from __future__ import annotations

from unittest.mock import call, patch

import pytest

from meta_package_manager.managers.homebrew import Brew, Cask


@pytest.mark.parametrize(
    "package_id",
    (
        "wget",
        "ffmpeg",
        "python@3.14",
        "firefox",
    ),
)
@pytest.mark.parametrize("manager_class", (Brew, Cask))
def test_trust_tap_skips_core_packages(manager_class, package_id):
    """Core formulae and casks live on trusted taps and must not trigger trust."""
    manager = manager_class()
    with patch.object(manager, "run_cli") as run_cli:
        manager.trust_tap(package_id)
    run_cli.assert_not_called()


@pytest.mark.parametrize(
    "manager_class,package_id,tap_id",
    (
        (Brew, "gromgit/fuse/ntfs-3g-mac", "gromgit/fuse"),
        (Brew, "smudge/smudge/nightlight", "smudge/smudge"),
        (
            Cask,
            "homebrew/cask-versions/firefox-developer-edition",
            "homebrew/cask-versions",
        ),
    ),
)
def test_trust_tap_qualified_package(manager_class, package_id, tap_id):
    """Tap-qualified IDs are tapped (idempotent) and trusted before install."""
    manager = manager_class()
    with patch.object(manager, "run_cli") as run_cli:
        manager.trust_tap(package_id)
    assert run_cli.call_args_list == [
        call("tap", tap_id, auto_post_args=False),
        call("trust", package_id),
    ]


@pytest.mark.parametrize("manager_class", (Brew, Cask))
def test_install_routes_through_trust_tap(manager_class):
    """install() always calls trust_tap() so the gate is uniform across paths."""
    manager = manager_class()
    with (
        patch.object(manager, "trust_tap") as trust_tap,
        patch.object(manager, "run_cli") as run_cli,
    ):
        manager.install("gromgit/fuse/ntfs-3g-mac")
    trust_tap.assert_called_once_with("gromgit/fuse/ntfs-3g-mac")
    run_cli.assert_called_once_with(
        "install",
        "--quiet",
        "gromgit/fuse/ntfs-3g-mac",
    )
