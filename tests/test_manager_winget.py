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
`winget.exe` and are platform-agnostic.
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
        # `XP`-prefixed but wrong length (not 12 or 14 chars total).
        "XP123456789012345",
        # Empty.
        "",
    ),
)
def test_store_id_re_rejects(package_id):
    assert WinGet._store_id_re.match(package_id) is None


def test_parse_details_ignores_indented_upgrade_line(winget):
    """Regression test: the package-block split must not fire on indented
    `  winget [version]` lines under `Available Upgrades`."""
    output = dedent("""\
        (1/1) Git [Git.Git]
        Version: 2.37.3
        Publisher: The Git Development Community
        Origin Source: winget
        Available Upgrades:
          winget [2.45.1]
        """)

    blocks = list(winget._parse_details(output))
    assert blocks == [("Git", "Git.Git", "2.37.3", {"winget": "2.45.1"})]


# Two blocks captured verbatim from `winget list --upgrade-available --details` on
# the windows-2025 GitHub runner, winget 1.29.290. The image installs these
# applications with their own MSI and EXE installers, so winget prints no `Origin
# Source` line, yet `winget update --all` upgrades both.
RUNNER_UPGRADES = r"""
(1/20) AWS Command Line Interface v2 [Amazon.AWSCLI]
Version: 2.36.40.0
Publisher: Amazon Web Services
Local Identifier: ARP\Machine\X64\{9F6E7A28-2D5A-4592-91F3-B357BD1640CE}
Product Code: {9f6e7a28-2d5a-4592-91f3-b357bd1640ce}
Upgrade Code: {e1c1971c-384e-4d6d-8d02-f1ac48281cf8}
Installer Category: msi
Installed Scope: Machine
Installed Locale: en-US
Available Upgrades:
  winget [2.36.47]
(5/20) ImageMagick 7.1.2-25 Q16-HDRI (64-bit) (2026-06-04) [ImageMagick.ImageMagick]
Version: 7.1.2.25
Publisher: ImageMagick Studio LLC
Local Identifier: ARP\Machine\X64\ImageMagick 7.1.2 Q16-HDRI (64-bit)_is1
Product Code: imagemagick 7.1.2 q16-hdri (64-bit)_is1
Installer Category: exe
Installed Scope: Machine
Installed Location: C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\
Available Upgrades:
  winget [7.1.2.31]
"""


# Two blocks captured verbatim from `winget list --source winget --details` on the
# windows-2025 GitHub runner, winget 1.29.290: an application the image installed
# itself, which winget matches to its catalog, and one winget installed.
RUNNER_INSTALLED = r"""
(1/53) 7-Zip 26.03 (x64) [7zip.7zip]
Version: 26.03
Publisher: Igor Pavlov
Local Identifier: ARP\Machine\X64\7-Zip
Product Code: 7-zip
Installer Category: exe
Installed Scope: Machine
Installed Location: C:\Program Files\7-Zip\
(10/53) hyperfine [sharkdp.hyperfine]
Version: 1.20.0
Publisher: David Peter
Local Identifier: ARP\User\X64\sharkdp.hyperfine_Microsoft.Winget.Source_8wekyb3d8bbwe
Product Code: sharkdp.hyperfine_microsoft.winget.source_8wekyb3d8bbwe
Installer Category: portable
Installed Scope: User
Installed Architecture: X64
Installed Location: C:\Users\runneradmin\AppData\Local\Microsoft\WinGet\Packages\sharkdp.hyperfine_Microsoft.Winget.Source_8wekyb3d8bbwe
Origin Source: winget
"""


def test_installed_lists_every_catalog_match(winget, monkeypatch):
    calls = []

    def run_cli(*args, **kwargs):
        calls.append(args)
        return RUNNER_INSTALLED

    monkeypatch.setattr(winget, "run_cli", run_cli)

    assert [package.id for package in winget.installed] == [
        "7zip.7zip",
        "sharkdp.hyperfine",
    ]
    assert calls == [("list", "--source", "winget", "--details")]


def test_outdated_keeps_every_winget_upgrade(winget, monkeypatch):
    output = RUNNER_UPGRADES + dedent("""\
        (21/22) Some Store App [9PF4QZKKRZ7N]
        Version: 1.0.0
        Origin Source: msstore
        Available Upgrades:
          msstore [2.0.0]
        (22/22) Git [Git.Git]
        Version: 2.37.3
        Origin Source: winget
        Available Upgrades:
          msstore [2.40.0]
          winget [2.45.1]
        """)
    monkeypatch.setattr(winget, "run_cli", lambda *args, **kwargs: output)

    packages = {
        package.id: (str(package.installed_version), str(package.latest_version))
        for package in winget.outdated
    }
    assert packages == {
        "Amazon.AWSCLI": ("2.36.40.0", "2.36.47"),
        "ImageMagick.ImageMagick": ("7.1.2.25", "7.1.2.31"),
        "Git.Git": ("2.37.3", "2.45.1"),
    }


def test_parse_table_handles_short_header_line(winget):
    """Regression test: winget may emit a header line shorter than the
    separator (trailing spaces on the last column are trimmed). The separator
    must drive the column width so data rows that fill the full width do not
    trip the width assertion."""
    # Build a table where the header line is intentionally one char shorter
    # than the separator (last column lacks a trailing space) but data rows
    # match the separator length. Pre-fix code computed
    # `table_width = len(lines[0])` and tripped the
    # `len(line) <= table_width` assertion on the data row.
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
    # Native package first, Store packages last. `sorted` is stable so the
    # relative order within each group matches the input.
    assert ids == ["Alex313031.Codium", "XP99BNH2JZBBQR", "9PF4QZKKRZ7N"]
    assert str(results[0].latest_version) == "1.86.0"
    assert str(results[1].latest_version) == "msstore"
    assert str(results[2].latest_version) == "msstore"
