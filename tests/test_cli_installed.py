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

import json

import pytest

from meta_package_manager.tables import INSTALLED_COLUMNS

from .fake_manager import FakeManager
from .test_cli import (
    CLIQueryTests,
    CLITableTests,
    check_filtered_ids,
    check_packages_payload,
)


@pytest.fixture
def subcmd():
    return "installed"


class TestInstalled(CLITableTests, CLIQueryTests):
    columns_registry = INSTALLED_COLUMNS

    def test_json_parsing(self, invoke, subcmd):
        result = invoke("--table-format", "json", subcmd)
        check_packages_payload(result)

    @pytest.mark.parametrize(
        ("args", "expected_ids"),
        (
            # No query: every installed package is listed.
            ((), {"fake-pkg-alpha", "fake-pkg-beta"}),
            # Fuzzy query narrows the listing to matching IDs.
            (("alpha",), {"fake-pkg-alpha"}),
            (("BETA",), {"fake-pkg-beta"}),
            (("fake-pkg",), {"fake-pkg-alpha", "fake-pkg-beta"}),
            (("absent",), set()),
            # Exact query requires a verbatim ID or name match.
            (("--exact", "fake-pkg-alpha"), {"fake-pkg-alpha"}),
            (("--exact", "alpha"), set()),
        ),
    )
    def test_query_filter(self, invoke, fake_pool, args, expected_ids):
        result = invoke("--table-format", "json", "installed", *args)
        check_filtered_ids(result, expected_ids)


class OverlappingFakeManager(FakeManager):
    """A second fake, sharing one of its two packages with
    {class}`~tests.fake_manager.FakeManager`.
    """

    @property
    def installed(self):
        yield self.package(id="fake-pkg-alpha", installed_version="1.0.0")
        yield self.package(id="fake-pkg-gamma", installed_version="0.1.0")


@pytest.fixture
def overlapping_pool(patch_pool_with):
    """Select two fakes that both list `fake-pkg-alpha`."""
    return patch_pool_with(FakeManager(), OverlappingFakeManager())


def test_duplicates_keep_the_shared_packages(invoke, overlapping_pool):
    """`--duplicates` keeps the packages that more than one manager lists."""
    result = invoke("--table-format", "json", "installed", "--duplicates")
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert {
        mid: [package["id"] for package in data["packages"]]
        for mid, data in payload.items()
    } == {
        "fakemanager": ["fake-pkg-alpha"],
        "overlappingfakemanager": ["fake-pkg-alpha"],
    }


def test_duplicates_sort_the_table_by_package(invoke, overlapping_pool):
    """The table puts the copies of a package next to each other."""
    result = invoke("--verbosity", "INFO", "installed", "--duplicates")
    assert result.exit_code == 0
    assert (
        "Force table sorting on package ID because of --duplicates option."
    ) in result.stderr
    assert result.stdout.count("fake-pkg-alpha") == 2
    assert "fake-pkg-beta" not in result.stdout
    assert "fake-pkg-gamma" not in result.stdout
