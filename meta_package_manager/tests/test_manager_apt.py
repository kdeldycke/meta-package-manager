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
"""APT-specific tests."""

from __future__ import annotations

import subprocess

import pytest
from click_extra.tests.conftest import unless_linux


@pytest.fixture()
def exact_search():
    def _exact_search(package_id):
        process = subprocess.run(
            ("apt", "search", f"^{package_id}$"),
            capture_output=True,
            encoding="utf-8",
        )
        assert process.returncode == 0
        return process.stdout

    return _exact_search


@unless_linux
class TestAPT:
    def test_nonempty_exact_search_results(self, invoke, exact_search):
        # Search for a package by the exact name, and check that apt finds it.
        output = exact_search("snapd")
        assert "snapd/" in output

        # Check that mpm recognizes that package.
        result = invoke("--apt", "search", "--exact", "snapd")
        assert result.exit_code == 0
        assert "snapd" in result.stdout
        assert "apt" in result.stdout
