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

"""Nala output tests.

These tests stub `run_cli` and replay the samples documented on
{class}`~meta_package_manager.managers.nala.Nala`. They never call `nala`.
"""

from __future__ import annotations

import pytest

from meta_package_manager.managers.nala import Nala

INSTALLED_RECORD = """\
vim 2:8.2.3995-1+b2 [Debian/sid main]
+-- is installed
`-- Vi IMproved - enhanced vi editor"""
"""`nala list --installed`, as the docstring of
{attr}`~meta_package_manager.managers.nala.Nala.installed` shows it."""

UPGRADABLE_RECORD = """\
vim 2:8.2.3995-1+b2 [Debian/sid main]
+-- is installed and upgradable to 2:8.2.4659-1
`-- Vi IMproved - enhanced vi editor"""
"""`nala list --upgradable`, as the docstring of
{attr}`~meta_package_manager.managers.nala.Nala.outdated` shows it."""

UNICODE_UPGRADABLE_RECORD = """\
vim 2:8.2.3995-1+b2 [Debian/sid main]
├── is installed and upgradable to 2:8.2.4659-1
└── Vi IMproved - enhanced vi editor"""
"""{data}`~tests.test_manager_nala.UPGRADABLE_RECORD` with the Unicode glyphs
`nala` uses when `LC_ALL=C` fails to select the ASCII pair."""


def test_installed(stub_run_cli):
    """A record gives its package and the version of its first line."""
    manager = Nala()
    stub_run_cli(manager, INSTALLED_RECORD)
    packages = [(p.id, str(p.installed_version)) for p in manager.installed]
    assert packages == [("vim", "2:8.2.3995-1+b2")]


@pytest.mark.parametrize(
    "output",
    (
        pytest.param(UPGRADABLE_RECORD, id="ascii-glyphs"),
        pytest.param(UNICODE_UPGRADABLE_RECORD, id="unicode-glyphs"),
    ),
)
def test_outdated(stub_run_cli, output):
    """The candidate comes from the status branch, the installed version from
    the first line, whichever glyphs draw the branches."""
    manager = Nala()
    stub_run_cli(manager, output)
    packages = [
        (p.id, str(p.installed_version), str(p.latest_version))
        for p in manager.outdated
    ]
    assert packages == [("vim", "2:8.2.3995-1+b2", "2:8.2.4659-1")]


def test_outdated_skips_a_record_without_candidate(stub_run_cli):
    """A record naming no version to move to is not an outdated package."""
    manager = Nala()
    stub_run_cli(manager, INSTALLED_RECORD)
    assert list(manager.outdated) == []


def test_search(stub_run_cli):
    """A search result is a record like those of `list`, its version the
    latest available.

    The docstring of {meth}`~meta_package_manager.managers.nala.Nala.search`
    documents the command alone, so the record of `list` stands in for its
    output: `nala` 0.18.2 prints both through one shared function.
    """
    manager = Nala()
    stub_run_cli(manager, INSTALLED_RECORD)
    packages = [
        (p.id, str(p.latest_version))
        for p in manager.search("vim", extended=False, exact=False)
    ]
    assert packages == [("vim", "2:8.2.3995-1+b2")]
