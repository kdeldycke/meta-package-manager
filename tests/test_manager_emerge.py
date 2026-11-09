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

import pytest

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


NEW_DEPENDENCIES_PLAN = """\

These are the packages that would be merged, in order:

Calculating dependencies  ... done!
Dependency resolution took 5.36 s (backtrack: 2/20).

[binary  N g   ] dev-perl/Error                                        [0.170.300-r1-2]              USE="-test" PERL_FEATURES="(-debug) -ithreads (-quadmath)" 
[binary  N g   ] dev-perl/Crypt-URandom                                [0.550.0-1]                   USE="-test" PERL_FEATURES="(-debug) -ithreads (-quadmath)" 
[binary  N g   ] dev-perl/TimeDate                                     [2.330.0-r1-4]                USE="-test" PERL_FEATURES="(-debug) -ithreads (-quadmath)" 
[binary  N g   ] dev-perl/Net-SSLeay                                   [1.960.0-r1-1]                USE="-examples -minimal -test" PERL_FEATURES="(-debug) -ithreads (-quadmath)" 
[binary  N g   ] virtual/perl-Digest-MD5                               [2.590.0-r1-1]               
[binary  N g   ] virtual/perl-Digest-SHA                               [6.40.0-r3-1]                
[binary  NSg   ] dev-build/autoconf                                    [2.73-r2-1]                  [2.72-r7]
[binary  N g   ] dev-perl/Digest-HMAC                                  [1.50.0-2]                    USE="-test" PERL_FEATURES="(-debug) -ithreads (-quadmath)" 
[binary  N g   ] dev-perl/IO-Socket-SSL                                [2.95.0-2]                    USE="-examples -idn -test" PERL_FEATURES="(-debug) -ithreads (-quadmath)" 
[binary  N g   ] virtual/perl-libnet                                   [3.150.0-r3-1]                USE="ssl" 
[binary  N g   ] dev-perl/Authen-SASL                                  [2.200.0-1]                   USE="-kerberos -test" PERL_FEATURES="(-debug) -ithreads (-quadmath)" 
[binary  N g   ] dev-perl/MailTools                                    [2.220.0-2]                   USE="-examples -test" PERL_FEATURES="(-debug) -ithreads (-quadmath)" 
[binary  N g   ] dev-vcs/git                                           [2.55.0-1]                    USE="curl gpg iconv nls pcre perl rust safe-directory webdav -cgi -cvs -debug -doc -highlight -keyring -perforce (-selinux) -subversion -test -tk -xinetd" PYTHON_SINGLE_TARGET="python3_14 -python3_12 -python3_13" 
[ebuild     U *] sys-process/htop                                      [9999]                       [3.5.3]

 * IMPORTANT: 26 news items need reading for repository 'gentoo'.
 * Use eselect news read to view new items.

"""  # noqa: E501
"""`emerge --color n --nospinner --update --deep --pretend --columns @world`,
once `sys-process/htop **` admits the live ebuild, which pulls in `dev-vcs/git`."""

DOWNGRADE_PLAN = """\

These are the packages that would be merged, in order:

Calculating dependencies  . ... done!
Dependency resolution took 2.77 s (backtrack: 0/20).

[ebuild     UD ] sys-process/htop                                      [3.5.1]                      [3.5.3] USE="-openvz% -vserver%" 

 * IMPORTANT: 26 news items need reading for repository 'gentoo'.
 * Use eselect news read to view new items.

"""  # noqa: E501
"""The same plan once `=sys-process/htop-3.5.3` is masked."""


@pytest.fixture
def emerge(monkeypatch):
    """A manager whose companion tools, like `qlist`, resolve in `/usr/bin`."""
    manager = Emerge()
    monkeypatch.setattr(
        manager, "sibling_cli", lambda name, **kwargs: Path("/usr/bin") / name
    )
    return manager


def test_exact_search_matches_the_bare_name(emerge, stub_run_cli):
    """An exact query names the package without the category its ID carries."""
    stub_run_cli(emerge, SEARCH_OUTPUT)
    results = emerge.refiltered_search("tmux", extended=False, exact=True)
    assert [package.id for package in results] == ["app-misc/tmux"]


def test_installed_rows_carry_the_bare_name(emerge, stub_run_cli):
    """The inventory splits each ID into its category and bare name."""
    stub_run_cli(emerge, INSTALLED_OUTPUT)
    packages = list(emerge.installed)
    assert [(p.id, p.name, str(p.installed_version)) for p in packages] == [
        ("app-admin/sudo", "sudo", "1.9.17_p2"),
        ("dev-perl/SGMLSpm", "SGMLSpm", "1.1-r2"),
        ("sys-process/htop", "htop", "3.5.3"),
    ]
    assert [p.id for p in packages if p.matches("htop", exact=True)] == [
        "sys-process/htop"
    ]


def test_outdated_reads_upgrades_only(emerge, stub_run_cli):
    """New dependencies, new slots and downgrades are not outdated packages."""
    stub_run_cli(emerge, NEW_DEPENDENCIES_PLAN)
    assert [
        (p.id, str(p.installed_version), str(p.latest_version)) for p in emerge.outdated
    ] == [("sys-process/htop", "3.5.3", "9999")]
    stub_run_cli(emerge, DOWNGRADE_PLAN)
    assert list(emerge.outdated) == []
