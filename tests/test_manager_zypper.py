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
"""openSUSE Zypper-specific tests.

Every payload below is captured output, from openSUSE Tumbleweed `20260830`
aarch64 running zypper `1.14.98`. The single-element ones are the point: a
freshly installed host reports exactly one pending update and answers an exact
search with exactly one solvable, and `xmltodict` renders a lone repeated
element as a bare mapping instead of a one-item list.
"""

from __future__ import annotations

import pytest

from meta_package_manager.managers.zypper import Zypper, _xml_items

ONE_UPDATE = """<?xml version='1.0'?>
<stream>
<message type="info">Loading repository data...</message>
<message type="info">Reading installed packages...</message>
<update-status version="0.6">
<update-list>
<update kind="package" name="libopenh264-8" edition="2.6.0-2.suse1699.10" arch="aarch64" edition-old="2.6.0~noopenh264-1.5"><summary>H.264 codec library</summary><license/><source url="http://codecs.opensuse.org/openh264/openSUSE_Tumbleweed" alias="repo-openh264"/></update></update-list>
</update-status>
</stream>
"""
"""`zypper --xmlout list-updates` on a host that is one package behind."""

NO_UPDATES = """<?xml version='1.0'?>
<stream>
<message type="info">Loading repository data...</message>
<message type="info">Reading installed packages...</message>
<update-status version="0.6">
<update-list/>
</update-status>
</stream>
"""
"""`zypper --xmlout list-updates` with nothing to upgrade: an empty element,
which `xmltodict` maps to `None` rather than to an empty list."""

ONE_SOLVABLE = """<?xml version='1.0'?>
<stream>
<message type="info">Loading repository data...</message>
<message type="info">Reading installed packages...</message>

<search-result version="0.0">
<solvable-list>
<solvable status="installed" name="gzip" kind="package" edition="1.14-3.1" arch="aarch64" repository="Main Repository (OSS)"/>
</solvable-list>
</search-result>
</stream>
"""
"""`zypper --xmlout search --details --type package --match-exact gzip`: the
ordinary shape of an exact search, not a corner case."""

MANY_SOLVABLES = """<?xml version='1.0'?>
<stream>
<message type="info">Loading repository data...</message>
<message type="info">Reading installed packages...</message>

<search-result version="0.0">
<solvable-list>
<solvable status="not-installed" name="bgzip" kind="package" edition="1.21-1.6" arch="aarch64" repository="Main Repository (OSS)"/>
<solvable status="not-installed" name="busybox-gzip" kind="package" edition="1.38.0-42.2" arch="noarch" repository="Main Repository (OSS)"/>
<solvable status="installed" name="gzip" kind="package" edition="1.14-3.1" arch="aarch64" repository="Main Repository (OSS)"/>
<solvable status="not-installed" name="igzip" kind="package" edition="2.32.1-1.3" arch="aarch64" repository="Main Repository (OSS)"/>
<solvable status="not-installed" name="perl-PerlIO-gzip" kind="package" edition="0.20-1.41" arch="aarch64" repository="Main Repository (OSS)"/>
<solvable status="not-installed" name="zstd-gzip" kind="package" edition="1.5.7-6.1" arch="aarch64" repository="Main Repository (OSS)"/>
</solvable-list>
</search-result>
</stream>
"""
"""`zypper --xmlout search --details --type package gzip`."""

NO_SOLVABLE = """<?xml version='1.0'?>
<stream>
<message type="info">Loading repository data...</message>
<message type="info">Reading installed packages...</message>
<message type="info">No matching items found.</message>
</stream>
"""
"""A search matching nothing drops the whole `search-result` element."""


@pytest.mark.parametrize(
    ("parent", "expected"),
    (
        pytest.param(None, [], id="parent-is-none"),
        pytest.param({}, [], id="parent-is-empty"),
        pytest.param({"other": "x"}, [], id="key-absent"),
        pytest.param({"k": {"@name": "gzip"}}, [{"@name": "gzip"}], id="lone-mapping"),
        pytest.param(
            {"k": [{"@name": "gzip"}]}, [{"@name": "gzip"}], id="one-item-list"
        ),
        pytest.param(
            {"k": [{"@name": "gzip"}, {"@name": "bgzip"}]},
            [{"@name": "gzip"}, {"@name": "bgzip"}],
            id="many",
        ),
    ),
)
def test_xml_items_normalises_every_shape(parent, expected):
    """`xmltodict` renders repeated elements in three shapes, and only one of
    them is iterable as a list of children."""
    assert _xml_items(parent, "k") == expected


@pytest.mark.parametrize(
    ("output", "expected"),
    (
        pytest.param(ONE_UPDATE, ["libopenh264-8"], id="one-update"),
        pytest.param(NO_UPDATES, [], id="no-updates"),
        pytest.param("", [], id="no-output"),
    ),
)
def test_outdated_reads_any_number_of_updates(stub_run_cli, output, expected):
    manager = Zypper()
    stub_run_cli(manager, output)
    assert [package.id for package in manager.outdated] == expected


def test_outdated_reads_the_update_versions(stub_run_cli):
    manager = Zypper()
    stub_run_cli(manager, ONE_UPDATE)
    package = next(iter(manager.outdated))
    assert str(package.latest_version) == "2.6.0-2.suse1699.10"
    assert str(package.installed_version) == "2.6.0~noopenh264-1.5"


@pytest.mark.parametrize(
    ("output", "expected"),
    (
        pytest.param(ONE_SOLVABLE, ["gzip"], id="one-solvable"),
        pytest.param(
            MANY_SOLVABLES,
            ["bgzip", "busybox-gzip", "gzip", "igzip", "perl-PerlIO-gzip", "zstd-gzip"],
            id="many-solvables",
        ),
        pytest.param(NO_SOLVABLE, [], id="no-solvable"),
        pytest.param("", [], id="no-output"),
    ),
)
def test_search_reads_any_number_of_solvables(stub_run_cli, output, expected):
    manager = Zypper()
    stub_run_cli(manager, output)
    results = manager.search("gzip", extended=False, exact=False)
    assert sorted(package.id for package in results) == sorted(expected)


@pytest.mark.parametrize(
    ("output", "expected"),
    (
        pytest.param(ONE_SOLVABLE, ["gzip"], id="one-solvable"),
        pytest.param(NO_SOLVABLE, [], id="no-solvable"),
    ),
)
def test_installed_reads_any_number_of_solvables(stub_run_cli, output, expected):
    """`installed` shares `_search` with `search`, so it shares its shapes."""
    manager = Zypper()
    stub_run_cli(manager, output)
    assert [package.id for package in manager.installed] == expected
