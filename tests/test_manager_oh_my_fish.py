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

"""Oh My Fish output tests.

These tests stub `run_cli` and replay the samples documented on
{class}`~meta_package_manager.managers.oh_my_fish.OhMyFish`. They never call
`fish` or `omf`.
"""

from __future__ import annotations

from meta_package_manager.managers.oh_my_fish import OhMyFish

LIST_OUTPUT = """\
Plugins
bang-bang     brew          fish-spec     osx
percol        pyenv         tab           z

Themes
agnoster      bobthefish    default       scorphish"""
"""`omf list`, as the docstring of
{attr}`~meta_package_manager.managers.oh_my_fish.OhMyFish.installed` shows it."""


def test_installed_reads_every_column(capture_run_cli):
    """Every name of both sections is a package, in the order printed, and the
    two section headers are not.
    """
    manager = OhMyFish()
    calls = capture_run_cli(manager, LIST_OUTPUT)
    packages = list(manager.installed)
    assert [p.id for p in packages] == [
        "bang-bang",
        "brew",
        "fish-spec",
        "osx",
        "percol",
        "pyenv",
        "tab",
        "z",
        "agnoster",
        "bobthefish",
        "default",
        "scorphish",
    ]
    # Oh My Fish records no revision per package.
    assert {p.installed_version for p in packages} == {None}
    assert calls == [("list",)]
