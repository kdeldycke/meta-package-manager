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
"""TazPkg output tests.

They replay what TazPkg 5.9.5 printed on SliTaz 5.0 with `--output=raw`, so they
neither need `tazpkg` nor a SliTaz host.
"""

from __future__ import annotations

from meta_package_manager.managers.tazpkg import Tazpkg

SEARCH_OUTPUT = """\

Search result for "nano"
================================================================================
Installed packages
--------------------------------------------------------------------------------
nano                    9.0               utilities
nanochess               1.0               games
================================================================================
2 installed packages found for "nano"

Available packages
--------------------------------------------------------------------------------
nano                    9.0               utilities
nano-doc                9.0               utilities
nano-lang               9.0               utilities
nanochess               1.0               games
nanoshot                0.2.15            utilities
================================================================================
5 available packages found for "nano"

"""
"""`tazpkg search nano`."""


def replaying(monkeypatch, output: str) -> Tazpkg:
    """A manager whose every command prints `output`."""
    manager = Tazpkg()
    monkeypatch.setattr(manager, "run_cli", lambda *args, **kwargs: output)
    return manager


def test_search_reports_an_installed_match_once(monkeypatch):
    """An installed match also listed by the mirror is one result, not two."""
    manager = replaying(monkeypatch, SEARCH_OUTPUT)
    results = [
        (package.id, str(package.latest_version))
        for package in manager.search("nano", extended=False, exact=False)
    ]
    assert results == [
        ("nano", "9.0"),
        ("nano-doc", "9.0"),
        ("nano-lang", "9.0"),
        ("nanochess", "1.0"),
        ("nanoshot", "0.2.15"),
    ]
