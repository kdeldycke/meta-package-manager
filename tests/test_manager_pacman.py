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
"""Host checks of the `pacman` family that need no `pacman` binary."""

from __future__ import annotations

import os

import pytest
from extra_platforms.pytest import skip_windows

from meta_package_manager.managers import pacman
from meta_package_manager.managers.pacman import (
    Aura,
    DkpPacman,
    Pacaur,
    Pacman,
    Paru,
    Pikaur,
    Trizen,
    Yay,
)

GUARDED_MANAGERS = (Aura, Pacaur, Pacman, Paru, Pikaur, Trizen, Yay)
"""The system `pacman` and the AUR helpers that hand their upgrades to it."""


@pytest.fixture
def guard(monkeypatch, tmp_path):
    """Move the Omarchy update guard and its override into `tmp_path`.

    Returns both paths, neither of which exists yet.
    """
    hook = tmp_path / "share" / "00-omarchy-update-guard.hook"
    override = tmp_path / "etc" / "00-omarchy-update-guard.hook"
    hook.parent.mkdir()
    override.parent.mkdir()
    monkeypatch.setattr(pacman, "OMARCHY_UPDATE_GUARD", hook)
    monkeypatch.setattr(pacman, "OMARCHY_UPDATE_GUARD_OVERRIDE", override)
    return hook, override


@pytest.mark.parametrize("manager_class", GUARDED_MANAGERS)
def test_omarchy_guard_skips_upgrade_all(manager_class, guard):
    """The hook file alone decides."""
    hook, _ = guard
    manager = manager_class()

    assert manager.upgrade_all_skip_reason is None

    hook.touch()
    assert manager.upgrade_all_skip_reason == (
        f"Omarchy's update guard ({hook}) aborts each full upgrade that "
        "`omarchy update` did not start. Run `omarchy update` instead."
    )


@pytest.mark.parametrize("manager_class", GUARDED_MANAGERS)
def test_overridden_guard_leaves_upgrade_all_to_pacman(manager_class, guard):
    """A file of the same name in the override directory replaces the hook."""
    hook, override = guard
    hook.touch()
    override.write_text("[Trigger]\n", encoding="UTF-8")

    assert manager_class().upgrade_all_skip_reason is None


@skip_windows
@pytest.mark.parametrize("manager_class", GUARDED_MANAGERS)
def test_disabled_guard_leaves_upgrade_all_to_pacman(manager_class, guard):
    """A symlink to the null device disables the hook."""
    hook, override = guard
    hook.touch()
    override.symlink_to(os.devnull)

    assert manager_class().upgrade_all_skip_reason is None


def test_dkp_pacman_ignores_omarchy_guard(guard):
    """devkitPro's `pacman` never runs the hooks of the system `pacman`."""
    hook, _ = guard
    hook.touch()

    assert DkpPacman().upgrade_all_skip_reason is None
