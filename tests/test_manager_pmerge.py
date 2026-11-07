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
"""pkgcore `pmerge` search tests.

They replay what `pquery` printed for pkgcore 0.12.48 on a Gentoo stage3, so they
need neither pkgcore nor a Gentoo host.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from meta_package_manager.managers.pmerge import Pmerge

NAME_OUTPUT = (
    "games-misc/nyancat=1.5.2=Nyancat in your terminal, rendered through ANSI "
    "escape sequences\n"
)
"""`pquery --color no --max --format {category}/{package}={fullver}={description}
nyancat`."""


def replaying(monkeypatch, output: str) -> tuple[Pmerge, list[tuple[str, ...]]]:
    """A manager whose every `pquery` call prints `output`, and the calls it made."""
    manager = Pmerge()
    calls: list[tuple[str, ...]] = []

    def run_cli(*args, **kwargs) -> str:
        calls.append(args)
        return output

    monkeypatch.setattr(manager, "run_cli", run_cli)
    monkeypatch.setattr(
        manager, "sibling_cli", lambda name, **kwargs: Path("/usr/bin") / name
    )
    return manager, calls


def test_exact_search_matches_the_bare_name(monkeypatch):
    """An exact query names the package without the category its ID carries."""
    manager, _ = replaying(monkeypatch, NAME_OUTPUT)
    results = manager.refiltered_search("nyancat", extended=False, exact=True)
    assert [package.id for package in results] == ["games-misc/nyancat"]


@pytest.mark.parametrize(
    ("query", "extended", "targets"),
    (
        ("nyan", False, [("*nyan*",)]),
        ("nyan", True, [("*nyan*",), ("--description", "nyan")]),
        ("c++", True, [("*c++*",), ("--description", r"c\+\+")]),
        ("games-misc/nyan", False, [("*games-misc/nyan*",)]),
        # `pquery` refuses a glob holding a space, and no name holds one.
        ("ANSI escape", True, [("--description", "ANSI escape")]),
        ("ANSI escape", False, []),
    ),
)
def test_search_globs_only_what_pquery_accepts(monkeypatch, query, extended, targets):
    """A name glob is only built from characters `pquery` accepts in one."""
    manager, calls = replaying(monkeypatch, "")
    tuple(manager.search(query, extended=extended, exact=False))
    # Each call opens on `--max --format <format>`, then carries its target.
    assert [call[3:] for call in calls] == targets
