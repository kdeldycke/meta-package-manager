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
"""GNU Guix output tests.

They replay what Guix printed on Guix System `aarch64-linux`: release `1.5.0`, and
master commit `5ef098e1` once `guix pull` ran. So they need neither `guix` nor a
Guix host.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from meta_package_manager.managers.guix import Guix

LIST_INSTALLED = (
    "hello          \t2.12.2\tout\t/gnu/store/8qjzxdk26p8c5nyj98s3321vbkmv9za0-hello-2.12.2\n"
    "lua            \t5.1.5 \tout\t/gnu/store/sq2sj9gj8bqzgv493249xd8gzhhw1f0x-lua-5.1.5\n"
    "glib           \t2.83.3\tout\t/gnu/store/h95r1yvlbrlqap6l8fsdzp7lpxair7sv-glib-2.83.3\n"
    "glib           \t2.83.3\tbin\t/gnu/store/06w4p65r8hli2qnsdsnp0l8r1zghz5qr-glib-2.83.3-bin\n"
    "glib-networking\t2.78.1\tout\t/gnu/store/n4nicicydz8d24m2qi3ddwlcxlr534qn-glib-networking-2.78.1\n"
)
"""`guix package --list-installed`, with the `bin` output of `glib` installed."""

UPGRADE_REPORT = (
    "guix upgrade: warning: Consider running 'guix pull' followed by\n"
    "'guix package -u' to get up-to-date packages and security updates.\n"
    "\n"
    "The following package would be upgraded:\n"
    "   lua 5.1.5 → 5.4.8\n"
    "\n"
)
"""What `guix upgrade --dry-run` writes to `<stderr>`, with `<stdout>` empty."""

PULLED_UPGRADE_REPORT = (
    "The following packages would be upgraded:\n"
    "   glib            2.83.3 → 2.86.0\n"
    "   glib-networking 2.78.1 → 2.80.1\n"
    "   glib:bin        2.83.3 → 2.86.0\n"
    "   hello           2.12.2 → 2.12.3\n"
    "   lua             5.1.5 → 5.5.0\n"
    "\n"
    "22.6 MB would be downloaded\n"
)
"""The same report once `guix pull` ran: padded names, and one row per output."""

SEARCH_OUTPUT = (
    "name: cowsay\n"
    "version: 3.8.4\n"
    "outputs:\n"
    "+ out: everything\n"
    "systems: x86_64-linux mips64el-linux aarch64-linux powerpc64le-linux\n"
    "+ i686-linux armhf-linux powerpc-linux\n"
    "dependencies: perl@5.36.0\n"
    "location: gnu/packages/games.scm:1431:2\n"
    "homepage: https://web.archive.org/web/20071026043648/http://www.nog.net:80/~tony/warez/cowsay.shtml\n"
    "license: GPL 3+\n"
    "synopsis: Speaking cow text filter  \n"
    "description: Cowsay is basically a text filter.  Send some text into it, and\n"
    "+ you get a cow saying your text.  If you think a talking cow isn't enough, cows\n"
    "+ can think too: all you have to do is run `cowthink'.  If you're tired of cows,\n"
    "+ a variety of other ASCII-art messengers are available.\n"
    "relevance: 32\n"
    "\n"
    "name: python-snakesay\n"
    "version: 0.10.4\n"
    "outputs:\n"
    "+ out: everything\n"
    "systems: x86_64-linux mips64el-linux aarch64-linux powerpc64le-linux\n"
    "+ i686-linux armhf-linux powerpc-linux\n"
    "dependencies: python-pytest@8.4.1 python-setuptools@80.9.0\n"
    "location: gnu/packages/python-xyz.scm:2293:2\n"
    "homepage: https://github.com/pythonanywhere/snakesay\n"
    "license: Expat\n"
    "synopsis: Like `cowsay' but with Python flavor  \n"
    "description: This package provides a simple ASCII art pictures generator of a\n"
    "+ Snake with a message.\n"
    "relevance: 3\n"
    "\n"
)
"""`guix search cowsay`, whose synopses end with two spaces."""

SEARCH_GTK_OUTPUT = (
    "name: gtk+\n"
    "version: 3.24.51\n"
    "outputs:\n"
    "+ bin: executable programs and scripts\n"
    "+ out: everything else\n"
    "systems: x86_64-linux aarch64-linux\n"
    "dependencies: at-spi2-core@2.52.0 cairo@1.18.4 colord-minimal@1.4.6\n"
    "+ cups@2.4.14 docbook-xml@4.3 docbook-xsl@1.79.2-0.fe16c90\n"
    "+ fontconfig-minimal@2.14.0 freetype@2.13.3 fribidi@1.0.12\n"
    "+ gettext-minimal@0.23.1 glib@2.83.3 gobject-introspection@1.82.0\n"
    "+ graphene@1.10.8 harfbuzz@11.4.4 hicolor-icon-theme@0.17 iso-codes@4.5.0\n"
    "+ json-glib-minimal@1.10.0 libcloudproviders-minimal@0.3.6 libepoxy@1.5.10\n"
    "+ librsvg@2.58.5 libx11@1.8.12 libxcomposite@0.4.6 libxcursor@1.2.3\n"
    "+ libxdamage@1.1.6 libxext@1.3.6 libxfixes@6.0.1 libxi@1.8.2 libxinerama@1.1.5\n"
    "+ libxkbcommon@1.11.0 libxml2@2.14.6 libxrandr@1.5.4 libxrender@0.9.12\n"
    "+ libxslt@1.1.43 mesa@25.2.3 pango@1.54.0 pkg-config@0.29.2\n"
    "+ python-wrapper@3.11.14 rest@0.8.1 sassc@3.6.2 wayland-protocols@1.45\n"
    "+ wayland@1.24.0 xorg-server@21.1.15\n"
    "location: gnu/packages/gtk.scm:1010:2\n"
    "homepage: https://www.gtk.org/\n"
    "license: LGPL 2.0+\n"
    "synopsis: Cross-platform toolkit for creating graphical user interfaces  \n"
    "description: GTK+, or the GIMP Toolkit, is a multi-platform toolkit for\n"
    "+ creating graphical user interfaces.  Offering a complete set of widgets, GTK+\n"
    "+ is suitable for projects ranging from small one-off tools to complete\n"
    "+ application suites.\n"
    "relevance: 30\n"
    "\n"
    "name: gtk+\n"
    "version: 2.24.33\n"
    "outputs:\n"
    "+ bin: executable programs and scripts\n"
    "+ doc: documentation\n"
    "+ debug: debug information\n"
    "+ out: everything else\n"
    "systems: x86_64-linux aarch64-linux\n"
    "dependencies: at-spi2-core@2.52.0 cairo@1.18.4 cups@2.4.14\n"
    "+ gettext-minimal@0.23.1 glib@2.83.3 gobject-introspection@1.82.0\n"
    "+ intltool@0.51.0 librsvg@2.58.5 libx11@1.8.12 libxcomposite@0.4.6\n"
    "+ libxcursor@1.2.3 libxdamage@1.1.6 libxext@1.3.6 libxi@1.8.2 libxinerama@1.1.5\n"
    "+ libxkbcommon@1.11.0 libxrandr@1.5.4 libxrender@0.9.12 libxshmfence@1.3.3\n"
    "+ pango@1.54.0 perl@5.36.0 pkg-config@0.29.2 python-wrapper@3.11.14\n"
    "+ xorg-server@21.1.15\n"
    "location: gnu/packages/gtk.scm:907:2\n"
    "homepage: https://www.gtk.org/\n"
    "license: LGPL 2.0+\n"
    "synopsis: Cross-platform toolkit for creating graphical user interfaces  \n"
    "description: GTK+, or the GIMP Toolkit, is a multi-platform toolkit for\n"
    "+ creating graphical user interfaces.  Offering a complete set of widgets, GTK+\n"
    "+ is suitable for projects ranging from small one-off tools to complete\n"
    "+ application suites.\n"
    "relevance: 30\n"
    "\n"
)
"""`guix search ^gtk\\+$`: two versions under one name, with different outputs."""


@pytest.fixture
def guix(monkeypatch):
    manager = Guix()
    monkeypatch.setattr(manager, "cli_errors", [])
    monkeypatch.setattr(manager, "cli_path", Path("/usr/bin/guix"), raising=False)
    return manager


def test_installed_strips_padding_and_names_outputs(guix, monkeypatch):
    monkeypatch.setattr(guix, "run_cli", lambda *args, **kwargs: LIST_INSTALLED)
    assert [
        (package.id, str(package.installed_version)) for package in guix.installed
    ] == [
        ("hello", "2.12.2"),
        ("lua", "5.1.5"),
        ("glib", "2.83.3"),
        ("glib:bin", "2.83.3"),
        ("glib-networking", "2.78.1"),
    ]


@pytest.mark.parametrize(
    ("report", "expected"),
    (
        pytest.param(UPGRADE_REPORT, [("lua", "5.1.5", "5.4.8")], id="one_row"),
        pytest.param(
            PULLED_UPGRADE_REPORT,
            [
                ("glib", "2.83.3", "2.86.0"),
                ("glib-networking", "2.78.1", "2.80.1"),
                ("glib:bin", "2.83.3", "2.86.0"),
                ("hello", "2.12.2", "2.12.3"),
                ("lua", "5.1.5", "5.5.0"),
            ],
            id="padded_rows",
        ),
    ),
)
def test_outdated_reads_the_report_from_stderr(guix, monkeypatch, report, expected):
    monkeypatch.setattr(guix, "_spawn", lambda *args, **kwargs: (0, "", report))
    assert [
        (package.id, str(package.installed_version), str(package.latest_version))
        for package in guix.outdated
    ] == expected


def test_search_strips_synopsis_padding(guix, monkeypatch):
    monkeypatch.setattr(guix, "run_cli", lambda *args, **kwargs: SEARCH_OUTPUT)
    assert [
        (package.id, str(package.latest_version), package.description)
        for package in guix.search("cowsay", extended=False, exact=False)
    ] == [
        ("cowsay", "3.8.4", "Speaking cow text filter"),
        ("python-snakesay", "0.10.4", "Like `cowsay' but with Python flavor"),
    ]


@pytest.mark.parametrize(
    ("query", "expected"),
    (
        pytest.param(r"^gtk\+$", [("gtk+", "3.24.51")], id="newest_version"),
        pytest.param("gtk+:bin", [("gtk+:bin", "3.24.51")], id="output"),
        pytest.param("gtk+:doc", [("gtk+:doc", "2.24.33")], id="older_output"),
        pytest.param("gtk+:apricot", [], id="missing_output"),
    ),
)
def test_search_reports_a_name_once(guix, monkeypatch, query, expected):
    """`mpm install` fails when its exact search returns more than one package."""
    monkeypatch.setattr(guix, "run_cli", lambda *args, **kwargs: SEARCH_GTK_OUTPUT)
    assert [
        (package.id, str(package.latest_version))
        for package in guix.search(query, extended=False, exact=False)
    ] == expected


def test_search_for_an_output_matches_the_name_alone(guix, monkeypatch):
    calls = []

    def record(*args, **kwargs):
        calls.append(args)
        return SEARCH_GTK_OUTPUT

    monkeypatch.setattr(guix, "run_cli", record)
    list(guix.search("gtk+:bin", extended=False, exact=False))
    assert calls == [("search", r"^gtk\+$")]


@pytest.mark.parametrize(
    ("package_id", "regexp"),
    (
        pytest.param("lua", "^lua$", id="anchored"),
        pytest.param("glib:bin", "^glib$", id="output_dropped"),
        pytest.param("gtk+", r"^gtk\+$", id="plus_escaped"),
        pytest.param("python-ruamel.yaml", r"^python-ruamel\.yaml$", id="dot_escaped"),
    ),
)
def test_upgrade_one_matches_the_name_alone(guix, package_id, regexp):
    """`guix upgrade glib` would also upgrade `glib-networking`."""
    assert guix.upgrade_one_cli(package_id)[1:] == ("upgrade", regexp)
