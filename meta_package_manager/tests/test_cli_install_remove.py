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

import pytest
from click_extra.tests.conftest import destructive

from ..pool import pool
from .conftest import all_manager_ids_and_dummy_package
from .test_cli import CLISubCommandTests


@pytest.fixture
def subcmd():
    return "install", "arrow"


class TestInstallRemove(CLISubCommandTests):
    """Install and remove operations are siblings and sensible, so we regroup them under
    the same test suite.

    Install mpm with itself when we can, so we can test externally contributed packaging.
    See: https://github.com/kdeldycke/meta-package-manager/issues/527
    """

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
        assert "Error: Missing argument 'PACKAGES_SPECS...'." in result.stderr

    @destructive
    @all_manager_ids_and_dummy_package
    def test_single_manager_install_and_remove(self, invoke, manager_id, package_id):
        result = invoke(f"--{manager_id}", "install", package_id)
        assert result.exit_code == 0
        self.check_manager_selection(
            result, {manager_id}, reference_set=pool.all_manager_ids
        )

        result = invoke(f"--{manager_id}", "remove", package_id)
        assert result.exit_code == 0
        self.check_manager_selection(
            result, {manager_id}, reference_set=pool.all_manager_ids
        )


destructive()(TestInstallRemove.test_stats)
destructive()(TestInstallRemove.test_default_all_managers)
destructive()(TestInstallRemove.test_manager_shortcuts)
destructive()(TestInstallRemove.test_manager_selection)
