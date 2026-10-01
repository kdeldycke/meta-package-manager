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
