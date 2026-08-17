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

from meta_package_manager.tables import INSTALLED_COLUMNS

from .test_cli import (
    CLIQueryTests,
    CLITableTests,
    check_packages_payload,
)


@pytest.fixture
def subcmd():
    return "orphans"


@pytest.mark.usefixtures("fake_pool")
class TestOrphans(CLITableTests, CLIQueryTests):
    """Pin the whole class to `fake_pool`.

    Unlike the other `CLITableTests` subcommands, `orphans` is implemented by
    only a subset of managers (all Linux, BSD or macOS tools), so no
    default-selected manager implements it on every platform: Windows has
    none. The inherited real-pool template tests would resolve there to
    `No manager selected.` instead of the `0` exit they assert, so the
    deterministic fake pool stands in on every host.
    """

    columns_registry = INSTALLED_COLUMNS

    def test_json_parsing(self, invoke, subcmd, fake_pool):
        result = invoke("--table-format", "json", subcmd)
        check_packages_payload(result, reference_set={fake_pool.id})

    @pytest.mark.parametrize(
        ("args", "expected_ids"),
        (
            # No query: every orphaned package is listed.
            ((), {"fake-orphan-alpha"}),
            # Fuzzy query narrows the listing to matching IDs.
            (("alpha",), {"fake-orphan-alpha"}),
            (("ORPHAN",), {"fake-orphan-alpha"}),
            (("absent",), set()),
            # Exact query requires a verbatim ID or name match.
            (("--exact", "fake-orphan-alpha"), {"fake-orphan-alpha"}),
            (("--exact", "alpha"), set()),
        ),
    )
    def test_query_filter(self, invoke, fake_pool, args, expected_ids):
        result = invoke("--table-format", "json", "orphans", *args)
        self.check_filtered_ids(result, expected_ids)
