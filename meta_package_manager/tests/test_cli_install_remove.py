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

from ..pool import pool
from .conftest import all_manager_ids_and_dummy_package
from .test_cli import CLISubCommandTests, check_manager_selection


@pytest.fixture
def subcmd():
    return "install", "arrow"


class TestInstallRemove(CLISubCommandTests):
    """Install and remove operations are siblings and sensible, so we regroup them under
    the same test suite.

    .. tip::

        Where we can, we invoke the ``install`` subcommand to install ``mpm`` with
        itself, so we can `test externally contributed packaging
        <https://github.com/kdeldycke/meta-package-manager/issues/527>`_.
    """

    @pytest.mark.parametrize("operation", ("install", "remove"))
    def test_no_package_id(self, invoke, operation):
        result = invoke(operation)
        assert result.exit_code == 2
        assert not result.stdout
        assert "Error: Missing argument 'PACKAGES_SPECS...'." in result.stderr

    @pytest.mark.destructive
    @all_manager_ids_and_dummy_package
    def test_single_manager_install_and_remove(self, invoke, manager_id, package_id):
        """
        .. caution

            ``strict_selection_match`` is set to ``False`` because the ``install``
            subcommand will not try all managers selected by default. So a strict
            match is not possible.

            That's because ``install`` subcommand try each user-selected manager until
            it find one providing the package we seek to install, after which the
            process stop.
        """
        result = invoke(f"--{manager_id}", "install", package_id)
        assert result.exit_code == 0
        check_manager_selection(
            result,
            {manager_id},
            reference_set=pool.all_manager_ids,
            strict_selection_match=False,
        )

        result = invoke(f"--{manager_id}", "remove", package_id)
        assert result.exit_code == 0
        check_manager_selection(
            result,
            {manager_id},
            reference_set=pool.all_manager_ids,
            strict_selection_match=False,
        )


pytest.mark.destructive()(TestInstallRemove.test_stats)
pytest.mark.destructive()(TestInstallRemove.test_manager_shortcuts)
pytest.mark.destructive()(TestInstallRemove.test_manager_selection)
