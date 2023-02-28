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

from ..base import Operations
from .conftest import default_manager_ids
from .test_cli import CLISubCommandTests


@pytest.fixture
def subcmd():
    return "backup"


class TestBackup(CLISubCommandTests):
    @staticmethod
    def evaluate_signals(mid, stdout, stderr):
        yield from (
            f"Dumping packages from {mid}..." in stderr,
            f"warning: {mid} does not implement {Operations.installed}" in stderr,
            # Common "not found" warning message.
            f"warning: Skip unavailable {mid} manager." in stderr,
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
        result = invoke(f"--{manager_id}", subcmd, "mpm-packages.toml")
        assert result.exit_code == 0
        assert "mpm-packages.toml" in result.stderr
        self.check_manager_selection(result, {manager_id})
