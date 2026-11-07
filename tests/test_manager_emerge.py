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
"""Portage `emerge` exact-match tests.

They replay what Portage 3.0.81.3 and `qlist` printed on a Gentoo arm64 host, so they
need neither Portage nor a Gentoo host.
"""

from __future__ import annotations

from pathlib import Path

from meta_package_manager.managers.emerge import Emerge

SEARCH_OUTPUT = """\
[gentoo] Local copy of remote index is within TTL and will be used.

[ Results for search key : %^tmux$ ]
Searching...

*  app-misc/tmux
      Latest version available: 3.6a
      Latest version installed: [ Not Installed ]
      Size of files: 734 KiB
      Homepage:      https://tmux.github.io/
      Description:   Terminal multiplexer
      License:       ISC

[ Applications found : 1 ]

"""
"""`emerge --color n --nospinner --search %^tmux$`."""

INSTALLED_OUTPUT = """\
app-admin/sudo-1.9.17_p2
dev-perl/SGMLSpm-1.1-r2
sys-process/htop-3.5.3
"""
"""Three rows of `qlist --installed --verbose --nocolor`."""


def replaying(monkeypatch, output: str) -> Emerge:
    """A manager whose every command prints `output`."""
    manager = Emerge()
    monkeypatch.setattr(manager, "run_cli", lambda *args, **kwargs: output)
    monkeypatch.setattr(
        manager, "sibling_cli", lambda name, **kwargs: Path("/usr/bin") / name
    )
    return manager


def test_exact_search_matches_the_bare_name(monkeypatch):
    """An exact query names the package without the category its ID carries."""
    manager = replaying(monkeypatch, SEARCH_OUTPUT)
    results = manager.refiltered_search("tmux", extended=False, exact=True)
    assert [package.id for package in results] == ["app-misc/tmux"]


def test_installed_rows_carry_the_bare_name(monkeypatch):
    """The inventory splits each ID into its category and bare name."""
    manager = replaying(monkeypatch, INSTALLED_OUTPUT)
    packages = list(manager.installed)
    assert [(p.id, p.name, str(p.installed_version)) for p in packages] == [
        ("app-admin/sudo", "sudo", "1.9.17_p2"),
        ("dev-perl/SGMLSpm", "SGMLSpm", "1.1-r2"),
        ("sys-process/htop", "htop", "3.5.3"),
    ]
    assert [p.id for p in packages if p.matches("htop", exact=True)] == [
        "sys-process/htop"
    ]
