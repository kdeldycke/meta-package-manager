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
"""IPS exact-match tests.

They replay what IPS printed on OpenIndiana Hipster, so they need neither IPS nor
an illumos host.
"""

from __future__ import annotations

from meta_package_manager.managers.ips import IPS

INSTALLED_OUTPUT = """\
SUNWcs                                            0.5.11-2026.0.0.23029      i--
SUNWcsd                                           0.5.11-2026.0.0.23029      i--
archiver/gnu-tar                                  1.35-2023.0.0.0            i--
audio/audio-utilities                             0.5.11-2026.0.0.23029      i--
audio/lame                                        3.100-2025.0.0.3           i--
"""
"""Five rows of `pkg list -H --no-refresh`."""

SEARCH_OUTPUT = (
    "pkg:/SUNWcs@0.5.11-2026.0.0.23029\topenindiana.org\n"
    "pkg:/archiver/gnu-tar@1.35-2023.0.0.0\topenindiana.org\n"
    "pkg:/archiver/ofarc@1.5.1-2026.0.0.0\topenindiana.org\n"
    "pkg:/developer/quilt@0.69-2026.0.0.2\topenindiana.org\n"
    "pkg:/library/perl-5/archive-tar@3.4-2025.0.0.1\topenindiana.org\n"
)
"""`pkg search -H -p tar`, whose columns are tab-separated."""


def test_installed_rows_carry_the_bare_name(stub_run_cli):
    """Each name is split into its path and its last component."""
    manager = IPS()
    stub_run_cli(manager, INSTALLED_OUTPUT)
    packages = list(manager.installed)
    assert [(p.id, p.name) for p in packages] == [
        ("SUNWcs", "SUNWcs"),
        ("SUNWcsd", "SUNWcsd"),
        ("archiver/gnu-tar", "gnu-tar"),
        ("audio/audio-utilities", "audio-utilities"),
        ("audio/lame", "lame"),
    ]
    assert [p.id for p in packages if p.matches("gnu-tar", exact=True)] == [
        "archiver/gnu-tar"
    ]


def test_exact_search_matches_the_bare_name(stub_run_cli):
    """An exact query names the package without the path of its name."""
    manager = IPS()
    stub_run_cli(manager, SEARCH_OUTPUT)
    results = manager.refiltered_search("archive-tar", extended=False, exact=True)
    assert [package.id for package in results] == ["library/perl-5/archive-tar"]
