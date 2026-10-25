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

"""vcpkg output tests.

These tests stub `run_cli` and replay the samples documented on
{class}`~meta_package_manager.managers.vcpkg.VCPKG`. They never call `vcpkg`.
"""

from __future__ import annotations

import pytest

from meta_package_manager.managers.vcpkg import VCPKG

LIST_OUTPUT = """\
{
  "zlib:x64-linux": {
    "package_name": "zlib",
    "triplet": "x64-linux",
    "version": "1.3.1",
    "port_version": 0,
    "features": [],
    "desc": ["A compression library"]
  }
}"""
"""`vcpkg --classic list --x-json`, as the docstring of
{attr}`~meta_package_manager.managers.vcpkg.VCPKG.installed` shows it."""

REVISED_LIST_OUTPUT = """\
{
  "freexl:x64-linux": {
    "package_name": "freexl",
    "triplet": "x64-linux",
    "version": "2.0.0",
    "port_version": 2,
    "features": [],
    "desc": ["FreeXL is an open source library to extract valid data"]
  }
}"""
"""The record of {data}`~tests.test_manager_vcpkg.LIST_OUTPUT`, for the `freexl`
port of {data}`~tests.test_manager_vcpkg.SEARCH_COLUMN_OUTPUT`, whose `2.0.0#2`
carries a port revision."""

SEARCH_COLUMN_OUTPUT = """\
cpr                      1.14.2           C++ Requests is a simple wrapper around libcurl
cpr[ssl]                                  Enable SSL support
duckdb[excel]                             Statically link the excel extension into DuckDB
freexl                   2.0.0#2          FreeXL is an open source library to extract valid data"""
"""`vcpkg --classic search excel`, as the docstring of
{meth}`~meta_package_manager.managers.vcpkg.VCPKG.search` shows it."""

SEARCH_LONG_NAMES_OUTPUT = """\
azure-security-keyvault-administration-cpp 4.0.0-beta.5#3 Microsoft Azure Key Vault Administration SDK for C++
azure-security-keyvault-certificates-cpp 4.2.1#5 Microsoft Azure Key Vault Certificates SDK for C++
azure-security-keyvault-keys-cpp 4.4.1#5  Microsoft Azure Key Vault Keys SDK for C++
azure-security-keyvault-secrets-cpp 4.2.1#5 Microsoft Azure Key Vault Secrets SDK for C++"""
"""The rows of `vcpkg --classic search keyvault` for the ports of the `2026.07.29`
registry, each name longer than the 24 columns vcpkg pads it to.

Laid out from the manifests by the rules of the `do_print` function of vcpkg, not
captured from a vcpkg run.
"""


@pytest.mark.parametrize(
    ("output", "expected"),
    (
        pytest.param(LIST_OUTPUT, [("zlib:x64-linux", "1.3.1")], id="no-revision"),
        pytest.param(
            REVISED_LIST_OUTPUT, [("freexl:x64-linux", "2.0.0#2")], id="revision"
        ),
    ),
)
def test_installed_reads_the_json_listing(stub_run_cli, output, expected):
    """The package is its full specification, and a non-zero port revision
    joins the version the way `vcpkg` renders it."""
    manager = VCPKG()
    stub_run_cli(manager, output)
    packages = [(p.id, str(p.installed_version)) for p in manager.installed]
    assert packages == expected


@pytest.mark.parametrize(
    "output",
    (
        pytest.param("", id="empty-output"),
        pytest.param("{}", id="nothing-installed"),
        pytest.param('{"zlib:x64-linux": "1.3.1"}', id="record-not-a-table"),
    ),
)
def test_installed_skips_what_is_not_a_record(stub_run_cli, output):
    """An answer with no record in it yields no package, and raises no error."""
    manager = VCPKG()
    stub_run_cli(manager, output)
    assert list(manager.installed) == []


@pytest.mark.parametrize(
    ("query", "output", "expected"),
    (
        pytest.param(
            "excel",
            SEARCH_COLUMN_OUTPUT,
            [("cpr", "1.14.2"), ("freexl", "2.0.0#2")],
            id="padded-names",
        ),
        pytest.param(
            "keyvault",
            SEARCH_LONG_NAMES_OUTPUT,
            [
                ("azure-security-keyvault-administration-cpp", "4.0.0-beta.5#3"),
                ("azure-security-keyvault-certificates-cpp", "4.2.1#5"),
                ("azure-security-keyvault-keys-cpp", "4.4.1#5"),
                ("azure-security-keyvault-secrets-cpp", "4.2.1#5"),
            ],
            id="long-names",
        ),
    ),
)
def test_search_reads_the_column_listing(capture_run_cli, query, output, expected):
    """A port gives its name and version, and the rows of its features are
    skipped. A name longer than its column still ends at the space after it."""
    manager = VCPKG()
    calls = capture_run_cli(manager, output)
    packages = [
        (p.id, str(p.latest_version))
        for p in manager.search(query, extended=False, exact=False)
    ]
    assert packages == expected
    assert calls == [("search", query)]


def test_search_empty_answer(stub_run_cli):
    """An empty answer is no match."""
    manager = VCPKG()
    stub_run_cli(manager, "")
    assert list(manager.search("excel", extended=False, exact=False)) == []
