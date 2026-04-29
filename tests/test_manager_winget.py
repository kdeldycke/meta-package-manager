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
"""WinGet-specific parsing tests.

These tests cover the pure-Python parsing/regex logic. They do not invoke
``winget.exe`` and are platform-agnostic.
"""

from __future__ import annotations

from textwrap import dedent

import pytest

from meta_package_manager.managers.winget import WinGet


@pytest.fixture
def winget():
    return WinGet()


@pytest.mark.parametrize(
    "package_id",
    (
        # 12-char product IDs.
        "9PF4QZKKRZ7N",
        "9NBLGGH4NNS1",
        "9MZ1SNWT0N5D",
        # 14-char extension IDs.
        "XP99BNH2JZBBQR",
        "XP8K0HKJFRXGCK",
    ),
)
def test_store_id_re_matches(package_id):
    assert WinGet._store_id_re.match(package_id)


@pytest.mark.parametrize(
    "package_id",
    (
        # Native winget IDs are dotted, mixed-case identifiers.
        "Microsoft.PowerToys",
        "Mozilla.Firefox",
        "Alex313031.Codium",
        "VSCodium.VSCodium",
        # Lowercase 12-char string is not a Store ID.
        "abcdefghijkl",
        # Wrong length: 11 and 13 chars.
        "9PF4QZKKRZ7",
        "9PF4QZKKRZ7NN",
        # ``XP``-prefixed but wrong length (not 12 or 14 chars total).
        "XP123456789012345",
        # Empty.
        "",
    ),
)
def test_store_id_re_rejects(package_id):
    assert WinGet._store_id_re.match(package_id) is None


def test_parse_details_ignores_indented_upgrade_line(winget):
    """Regression test: the package-block split must not fire on indented
    ``  winget [version]`` lines under ``Available Upgrades``."""
    output = dedent("""\
        (1/1) Git [Git.Git]
        Version: 2.37.3
        Publisher: The Git Development Community
        Origin Source: winget
        Available Upgrades:
          winget [2.45.1]
        """)

    blocks = list(winget._parse_details(output))
    assert len(blocks) == 1
    name, package_id, version, latest_version = blocks[0]
    assert name == "Git"
    assert package_id == "Git.Git"
    assert version == "2.37.3"
    assert latest_version == "2.45.1"


def test_parse_details_filter_by_source(winget):
    output = dedent("""\
        (1/2) Git [Git.Git]
        Version: 2.37.3
        Origin Source: winget

        (2/2) Some Store App [9PF4QZKKRZ7N]
        Version: Unknown
        Origin Source: msstore
        """)

    all_blocks = list(winget._parse_details(output))
    winget_only = list(winget._parse_details(output, filter_by_source=True))
    assert len(all_blocks) == 2
    assert len(winget_only) == 1
    assert winget_only[0][1] == "Git.Git"


def test_parse_table_handles_short_header_line(winget):
    """Regression test: winget may emit a header line shorter than the
    separator (trailing spaces on the last column are trimmed). The separator
    must drive the column width so data rows that fill the full width do not
    trip the width assertion."""
    # Build a table where the header line is intentionally one char shorter
    # than the separator (last column lacks a trailing space) but data rows
    # match the separator length. Pre-fix code computed
    # ``table_width = len(lines[0])`` and tripped the
    # ``len(line) <= table_width`` assertion on the data row.
    header = "Name              Id                Version      Source"
    data = "VSCodium          VSCodium.VSCodium 1.89.1.24130 winget "
    separator = "-" * len(data)
    assert len(header) < len(separator), "fixture sanity check"

    output = f"{header}\n{separator}\n{data}\n"
    rows = [list(row) for row in winget._parse_table(output)]
    assert len(rows) == 1
    assert rows[0][0] == "VSCodium"
    assert rows[0][1] == "VSCodium.VSCodium"


def test_parse_table_yields_nothing_on_empty_output(winget):
    assert list(winget._parse_table("")) == []


def test_build_package_native(winget):
    pkg = winget._build_package("Codium", "Alex313031.Codium", "1.86.2.24053")
    assert pkg.id == "Alex313031.Codium"
    assert pkg.name == "Codium"
    assert str(pkg.latest_version) == "1.86.2.24053"


@pytest.mark.parametrize(
    "package_id",
    ("9PF4QZKKRZ7N", "XP99BNH2JZBBQR"),
)
def test_build_package_store_uses_msstore_sentinel(winget, package_id):
    pkg = winget._build_package("Some App", package_id, "1.0.0")
    assert pkg.id == package_id
    assert str(pkg.latest_version) == "msstore"


def test_search_orders_native_before_store(winget, monkeypatch):
    """Microsoft Store entries must come after winget-native ones in the search
    output, regardless of the order winget returned them in."""
    rows = [
        "Store App         XP99BNH2JZBBQR    1.0.0        Tag: vscode     msstore",
        "Codium            Alex313031.Codium 1.86.0       Tag: vscode     winget ",
        "Other             9PF4QZKKRZ7N      2.0.0        Tag: vscode     msstore",
    ]
    width = max(len(row) for row in rows)
    header = "Name              Id                Version      Match           Source"
    table = "\n".join([header, "-" * width, *rows]) + "\n"

    monkeypatch.setattr(winget, "run_cli", lambda *a, **kw: table)

    results = list(winget.search("vscode", extended=True, exact=False))
    ids = [p.id for p in results]
    # Native package first, Store packages last. ``sorted`` is stable so the
    # relative order within each group matches the input.
    assert ids == ["Alex313031.Codium", "XP99BNH2JZBBQR", "9PF4QZKKRZ7N"]
    assert str(results[0].latest_version) == "1.86.0"
    assert str(results[1].latest_version) == "msstore"
    assert str(results[2].latest_version) == "msstore"
