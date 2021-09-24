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

from ..managers import pool
from .conftest import MANAGER_IDS, destructive
from .test_cli import CLISubCommandTests


@pytest.fixture
def subcmd():
    """Seed common subcommand tests with a dummy file and content to allow the
    CLI to not fail on required file input."""
    return "--manager", "pip", "install", "arrow"


class TestInstall(CLISubCommandTests):
    def test_no_package_id(self, invoke):
        result = invoke("install")
        assert result.exit_code == 2
        assert not result.stdout
        assert "Error: Missing argument 'PACKAGE_ID'." in result.stderr

    def test_no_manager(self, invoke):
        result = invoke("install", "dummy")
        assert result.exit_code == 2
        assert not result.stdout
        assert "critical: Only one package manager should be provided." in result.stderr

    def test_multiple_manager(self, invoke):
        result = invoke("--manager", "pip", "--manager", "npm", "install", "dummy")
        assert result.exit_code == 2
        assert not result.stdout
        assert "critical: Only one package manager should be provided." in result.stderr

    PACKAGE_IDS = {
        "apm": "markdown-pdf",
        "apt": "bat",
        "brew": "jpeginfo",
        "cask": "pngyu",
        "composer": "illuminate/contracts",
        "flatpak": "org.gnome.Dictionary",
        "gem": "markdown",
        "mas": "747648890",  # Telegram
        "npm": "raven",
        "opkg": "enigma2-hotplug",
        "pip": "arrow",
        "snap": "standard-notes",
        "vscode": "tamasfe.even-better-toml",
        "yarn": "markdown",
    }
    assert set(PACKAGE_IDS) == set(MANAGER_IDS)

    @destructive
    @pytest.mark.parametrize("mid,package_id", PACKAGE_IDS.items())
    def test_single_manager_install(self, invoke, mid, package_id):
        result = invoke("--manager", mid, "install", package_id)

        if pool()[mid].available:
            assert result.exit_code == 0
            self.check_manager_selection(result, {mid})
        else:
            assert result.exit_code == 2
            assert not result.stdout
            assert "critical: A package manager must be provided" in result.stderr


destructive()(TestInstall.test_options)

skip_multiple_manager = pytest.mark.skip(
    reason="mpm install only support one manager at a time"
)
skip_multiple_manager(TestInstall.test_default_all_managers)
skip_multiple_manager(TestInstall.test_manager_selection)
