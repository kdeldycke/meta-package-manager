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

from meta_package_manager.capabilities import Operations

from .conftest import default_manager_ids
from .test_cli import CLISubCommandTests


@pytest.fixture
def subcmd():
    # ``DEBUG`` level is required so that ``check_manager_selection`` can detect
    # skip/does-not-implement signals for implicitly selected managers. Those
    # messages are demoted to DEBUG when no explicit ``--<id>`` flag is passed.
    # INFO messages are a subset of DEBUG, so everything logged at INFO still
    # appears.
    return "--verbosity", "DEBUG", "backup"


class TestBackup(CLISubCommandTests):
    @staticmethod
    def evaluate_signals(mid, stdout, stderr):
        yield from (
            f":{mid}: Dumping packages..." in stderr,
            # The glued ``:<mid>:`` label form matches whatever level the
            # message lands at: demoted to DEBUG for implicit selection
            # (``mpm backup``), INFO for explicit ones (``mpm --<mid> backup``).
            f":{mid}: Does not implement {Operations.installed}" in stderr,
            f":{mid}: Skipped:" in stderr,
        )

    def test_default_all_managers_output_to_console(self, invoke, subcmd):
        result = invoke(subcmd)
        assert result.exit_code == 0
        assert "Print installed package list to <stdout>" in result.stderr
        self.check_manager_selection(result)

    def test_output_to_console(self, invoke, subcmd):
        result = invoke(subcmd, "-")
        assert result.exit_code == 0
        assert "Print installed package list to <stdout>" in result.stderr
        self.check_manager_selection(result)

    def test_output_to_file(self, invoke, subcmd):
        result = invoke(subcmd, "mpm-packages.toml")
        assert result.exit_code == 0
        assert "mpm-packages.toml" in result.stderr
        self.check_manager_selection(result)

    @default_manager_ids
    def test_single_manager_file_output(self, manager_id, invoke, subcmd):
        result = invoke(
            "--verbosity", "INFO", f"--{manager_id}", subcmd, "mpm-packages.toml"
        )
        assert "mpm-packages.toml" in result.stderr
        if result.exit_code == 2:
            assert not result.stdout
            assert "critical: No manager selected.\n" in result.stderr
        else:
            assert result.exit_code == 0
            self.check_manager_selection(result, {manager_id})
