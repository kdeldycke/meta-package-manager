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

"""FreeBSD `pkg` output tests.

These tests stub `run_cli` and replay the samples documented on
{class}`~meta_package_manager.managers.pkg.PKG`. They never call `pkg`.
"""

from __future__ import annotations

import pytest

from meta_package_manager.managers.pkg import PKG

SEARCH_OUTPUT = (
    '[{"name":"nyancat","origin":"net/nyancat","version":"1.5.2,1",'
    '"comment":"Animated telnet server that renders a loop of the nyan cat animation"}]'
)
"""`pkg search --raw --raw-format json-compact --search name nyancat`, as the
docstring of {meth}`~meta_package_manager.managers.pkg.PKG.search` shows it,
minus the `(...)` marker that truncates the record there."""

BASE_SEARCH_ARGS = ["search", "--raw", "--raw-format", "json-compact"]
"""The leading arguments of the three searches the docstring documents."""


@pytest.mark.parametrize(
    ("exact", "extended", "search_fields"),
    (
        pytest.param(False, False, ["--search", "name"], id="default"),
        pytest.param(True, False, ["--search", "name", "--exact"], id="exact"),
        pytest.param(
            False,
            True,
            ["--search", "name", "--search", "comment", "--search", "description"],
            id="extended",
        ),
    ),
)
def test_search(capture_run_cli, exact, extended, search_fields):
    """A match gives its name, comment and version, whichever of the three
    documented searches produced it."""
    manager = PKG()
    calls = capture_run_cli(manager, SEARCH_OUTPUT)
    packages = [
        (p.id, p.description, str(p.latest_version))
        for p in manager.search("nyancat", extended=extended, exact=exact)
    ]
    assert packages == [
        (
            "nyancat",
            "Animated telnet server that renders a loop of the nyan cat animation",
            "1.5.2,1",
        ),
    ]
    assert calls == [([*BASE_SEARCH_ARGS, *search_fields], "nyancat")]


def test_search_without_match(stub_run_cli):
    """A search matching nothing prints an empty array, which yields no
    package."""
    manager = PKG()
    stub_run_cli(manager, "[]")
    assert list(manager.search("nyancat", extended=False, exact=False)) == []
