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

"""MiKTeX output tests.

These tests stub `run_cli` and replay the samples documented on
{class}`~meta_package_manager.managers.miktex.MiKTeX`. They never call
`miktex`.
"""

from __future__ import annotations

import pytest

from meta_package_manager.managers.miktex import MiKTeX

LIST_OUTPUT = """\
true amsmath 2.17n
false zwpagelayout
true fancyhdr 4.0.3"""
"""The catalog listing, as the docstring of
{attr}`~meta_package_manager.managers.miktex.MiKTeX.installed` shows it."""


@pytest.mark.parametrize(
    ("output", "expected"),
    (
        pytest.param(
            LIST_OUTPUT,
            [("amsmath", "2.17n"), ("fancyhdr", "4.0.3")],
            id="catalog",
        ),
        # The `zwpagelayout` row once installed: its version is empty, as MiKTeX
        # versions often are.
        pytest.param("true zwpagelayout", [("zwpagelayout", None)], id="no-version"),
    ),
)
def test_installed_filters_the_catalog(capture_run_cli, output, expected):
    """Only the rows flagged as installed are packages, and an empty version
    is no version.
    """
    manager = MiKTeX()
    calls = capture_run_cli(manager, output)
    packages = [
        (p.id, None if p.installed_version is None else str(p.installed_version))
        for p in manager.installed
    ]
    assert packages == expected
    assert calls == [
        (
            "--disable-installer",
            "packages",
            "list",
            "--template",
            "{isInstalled} {id} {version}",
        ),
    ]
