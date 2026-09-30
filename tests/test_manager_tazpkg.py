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

import pytest

from meta_package_manager.execution import CLIError
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

INSTALL_OUTPUT = """\
Package "figlet-2.2.5.tazpkg" already in the cache

Installation of package "figlet"
================================================================================
A program for making large letters out of ordinary text.
--------------------------------------------------------------------------------
Copying package...                                                     Done
Extracting package...                                                  Done
Remember modified packages...                                          Done
Installing package...                                                  Done
Removing all tmp files...                                              Done
================================================================================
Package "figlet" (2.2.5) is installed.

"""
"""`tazpkg get-install figlet --forced`, which exits `0`."""

REFUSAL_OUTPUT = """\
Package "figlet-2.2.5.tazpkg" already in the cache


You need upgrade tazpkg first !

run tazpkg -gi tazpkg --forced then relaunch tazpkg -gi figlet


"""
"""`tazpkg get-install figlet --forced` while `/var/lock/tazpkgup.lock` exists,
which also exits `0`."""

OPERATIONS = (
    pytest.param(lambda manager: manager.install("figlet"), id="install"),
    pytest.param(lambda manager: manager.upgrade("figlet"), id="upgrade"),
)


def replaying(monkeypatch, output: str) -> Tazpkg:
    """A manager whose every command prints `output`."""
    manager = Tazpkg()
    monkeypatch.setattr(manager, "run_cli", lambda *args, **kwargs: output)
    monkeypatch.setattr(manager, "upgrade_one_cli", lambda *args, **kwargs: ("tazpkg",))
    monkeypatch.setattr(manager, "run", lambda *args, **kwargs: output)
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


@pytest.mark.parametrize("operation", OPERATIONS)
def test_completed_install_passes(monkeypatch, operation):
    """The control: a completed install is no failure."""
    manager = replaying(monkeypatch, INSTALL_OUTPUT)
    assert operation(manager) == INSTALL_OUTPUT
    assert manager.cli_errors == []


@pytest.mark.parametrize("operation", OPERATIONS)
def test_self_upgrade_refusal_fails_the_operation(monkeypatch, operation):
    """A refusal is a failure, recorded like a non-zero exit."""
    manager = replaying(monkeypatch, REFUSAL_OUTPUT)
    with pytest.raises(CLIError, match="tazpkg get-install tazpkg --forced"):
        operation(manager)
    assert len(manager.cli_errors) == 1
