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
"""``mpm dump`` CLI tests.

Drives the subcommand against the deterministic ``fake_pool``. The Brewfile
renderer it delegates to is unit-tested in :mod:`tests.test_brewfile`, and the
snapshot/merge/update flows shared with the ``backup`` alias live in
:mod:`tests.test_cli_backup`.
"""

from __future__ import annotations


def test_dump_query_filter_narrows_to_matches(invoke, fake_pool):
    """``dump --query`` keeps only installed packages matching the query."""
    result = invoke("dump", "--query", "alpha")
    assert result.exit_code == 0
    assert "fake-pkg-alpha" in result.stdout
    assert "fake-pkg-beta" not in result.stdout


def test_dump_without_query_lists_all(invoke, fake_pool):
    """Without a query, ``dump`` snapshots the full installed inventory."""
    result = invoke("dump")
    assert result.exit_code == 0
    assert "fake-pkg-alpha" in result.stdout
    assert "fake-pkg-beta" in result.stdout
