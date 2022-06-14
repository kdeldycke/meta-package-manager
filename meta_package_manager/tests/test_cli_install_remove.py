# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
# All Rights Reserved.
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

import pytest
from click_extra.tests.conftest import destructive

from ..pool import pool
from .test_cli import CLISubCommandTests


@pytest.fixture
def subcmd():
    return "install", "arrow"


class TestInstallRemove(CLISubCommandTests):
    """Install and remove operations are siblings and sensible, so we regroup them under
    the same test suite."""

    strict_selection_match = False
    """ Install sub-command try each user-selected manager until it find one providing
    the package we seek to install, after which the process stop. This mean not all
    managers will be called, so we allow the CLI output checks to partially match.
    """

    @pytest.mark.parametrize("operation", ("install", "remove"))
    def test_no_package_id(self, invoke, operation):
        result = invoke(operation)
        assert result.exit_code == 2
        assert not result.stdout
        assert "Error: Missing argument 'PACKAGE_ID'." in result.stderr

    PACKAGE_IDS = {
        "apm": "markdown-pdf",
        "apt": "wget",
        "apt-mint": "exiftool",
        "brew": "jpeginfo",
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
        "pacman": "manjaro-hello",
        "pip": "arrow",
        "pipx": "pycowsay",
        "snap": "standard-notes",
        "steamcmd": "740",
        "vscode": "tamasfe.even-better-toml",
        "yarn": "markdown",
        # Install mpm with itself:
        # https://aur.archlinux.org/packages/meta-package-manager
        "yay": "meta-package-manager",
        "yum": "usd",
        "zypper": "git",
    }
    assert set(PACKAGE_IDS) == set(pool.all_manager_ids)

    @destructive
    @pytest.mark.parametrize(
        "mid,package_id", (pytest.param(*v, id=v[0]) for v in PACKAGE_IDS.items())
    )
    def test_single_manager_install_and_remove(self, invoke, mid, package_id):
        result = invoke(f"--{mid}", "install", package_id)
        assert result.exit_code == 0
        self.check_manager_selection(result, {mid}, reference_set=pool.all_manager_ids)

        result = invoke(f"--{mid}", "remove", package_id)
        assert result.exit_code == 0
        self.check_manager_selection(result, {mid}, reference_set=pool.all_manager_ids)


destructive()(TestInstallRemove.test_stats)
destructive()(TestInstallRemove.test_default_all_managers)
destructive()(TestInstallRemove.test_manager_shortcuts)
destructive()(TestInstallRemove.test_manager_selection)
