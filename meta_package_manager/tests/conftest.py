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

from functools import partial
from operator import attrgetter

import pytest

# Pre-load invokation helpers to be used as pytest's fixture.
from click_extra.tests.conftest import create_config  # nopycln: import
from click_extra.tests.conftest import runner  # nopycln: import
from click_extra.tests.conftest import invoke as invoke_extra
from pytest import fixture, param

from ..cli import mpm
from ..pool import manager_classes, pool

""" Fixtures, configuration and helpers for tests. """


@fixture
def invoke(invoke_extra):
    return partial(invoke_extra, mpm)


@fixture(scope="class")
def subcmd():
    """Fixture used in ``test_cli_*.py`` files to set the sub-command arguments in all
    CLI calls.

    Must returns a string or an iterable of strings. Defaults to ``None``, which allows
    tests relying on this fixture to selectively skip running.
    """
    return None


PACKAGE_IDS = {
    "apm": "markdown-pdf",
    "apt": "wget",
    "apt-mint": "exiftool",
    # https://github.com/Hasnep/homebrew-tap/blob/main/Formula/meta-package-manager.rb
    "brew": "hasnep/tap/meta-package-manager",
    "cargo": "colorous",
    "cask": "pngyu",
    "choco": "ccleaner",
    "composer": "illuminate/contracts",
    "dnf": "usd",
    "emerge": "dev-vcs/git",
    "flatpak": "org.gnome.Dictionary",
    "gem": "markdown",
    "mas": "747648890",  # Telegram
    "npm": "raven",
    "opkg": "enigma2-hotplug",
    "pacaur": "manjaro-hello",
    "pacman": "manjaro-hello",
    # https://aur.archlinux.org/packages/meta-package-manager
    "paru": "meta-package-manager",
    # https://pypi.org/project/meta-package-manager
    "pip": "meta-package-manager",
    # https://pypi.org/project/meta-package-manager
    "pipx": "meta-package-manager",
    "scoop": "7zip",
    "snap": "standard-notes",
    "steamcmd": "740",
    "vscode": "tamasfe.even-better-toml",
    "yarn": "awesome-lint",
    # https://aur.archlinux.org/packages/meta-package-manager
    "yay": "meta-package-manager",
    "yum": "usd",
    "zypper": "git",
}
"""List of existing package IDs to install for each supported package manager.

Only to be used for destructive tests.
"""

assert set(PACKAGE_IDS) == set(pool.all_manager_ids)

# Collection of pre-computed parametrized decorators.

all_managers = pytest.mark.parametrize("manager", pool.values(), ids=attrgetter("id"))
available_managers = pytest.mark.parametrize(
    "manager", tuple(m for m in pool.values() if m.available), ids=attrgetter("id")
)

all_manager_ids = pytest.mark.parametrize("manager_id", pool.all_manager_ids)
maintained_manager_ids = pytest.mark.parametrize(
    "manager_id", pool.maintained_manager_ids
)
default_manager_ids = pytest.mark.parametrize("manager_id", pool.default_manager_ids)
unsupported_manager_ids = pytest.mark.parametrize(
    "manager_id", pool.unsupported_manager_ids
)

manager_classes = pytest.mark.parametrize(  # type: ignore[assignment]
    "manager_class", manager_classes, ids=attrgetter("name")
)

all_manager_ids_and_dummy_package = pytest.mark.parametrize(
    "manager_id,package_id", (param(*v, id=v[0]) for v in PACKAGE_IDS.items())
)
available_managers_and_dummy_package = pytest.mark.parametrize(
    "manager,package_id",
    (param(m, PACKAGE_IDS[mid], id=mid) for mid, m in pool.items() if m.available),
)
