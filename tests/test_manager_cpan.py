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
"""Perl CPAN listing tests.

`run_cli` is stubbed, so these tests never invoke `cpan` or `perl`. The
directories they list are real, since the manager tells a symlinked `@INC`
entry apart through the filesystem.
"""

from __future__ import annotations

import os

import pytest
from extra_platforms import is_any_windows

from meta_package_manager.managers.cpan import CPAN


def fake_cpan(monkeypatch, manager, inc, listings):
    """Answer the `@INC` probe with `inc`, and each `cpan -l` run with the next of
    `listings`. Returns the `(args, kwargs)` of every call."""
    calls: list[tuple[tuple, dict]] = []
    runs = iter(listings)

    def fake_run_cli(*args, **kwargs):
        calls.append((args, kwargs))
        if args[:1] == ("-e",):
            return "\n".join(inc)
        return next(runs)

    monkeypatch.setattr(manager, "run_cli", fake_run_cli)
    return calls


@pytest.mark.skipif(is_any_windows(), reason="A symlink needs privileges on Windows.")
def test_installed_adds_modules_behind_symlinked_inc(tmp_path, monkeypatch):
    """Modules in a symlinked `@INC` directory come from a second `cpan -l`, which
    never replaces a row of the first."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "perl").touch()
    site = tmp_path / "site"
    site.mkdir()
    core = tmp_path / "perl" / "5.40.1"
    core.mkdir(parents=True)
    linked = tmp_path / "perl" / "5.40"
    linked.symlink_to(core)

    manager = CPAN()
    manager.__dict__["cli_path"] = bin_dir / "cpan"
    monkeypatch.setenv("PERL5LIB", "/home/alice/perl5/lib/perl5")
    calls = fake_cpan(
        monkeypatch,
        manager,
        inc=(str(site), str(linked)),
        listings=(
            "Try::Tiny\t0.31\nstrict\t1.13",
            "App::Prove\t3.48\nstrict\t1.12\nwarnings\tundef",
        ),
    )

    packages = [
        (package.id, package.installed_version and str(package.installed_version))
        for package in manager.installed
    ]

    assert packages == [
        ("Try::Tiny", "0.31"),
        ("strict", "1.13"),
        ("App::Prove", "3.48"),
        ("warnings", None),
    ]
    env = calls[-1][1]["override_extra_env"]
    assert env["PERL5LIB"] == os.pathsep.join((
        str(core.resolve()),
        "/home/alice/perl5/lib/perl5",
    ))
    assert env["PERL_MM_USE_DEFAULT"] == "1"


@pytest.mark.parametrize(
    ("sibling_perl", "expected_calls"),
    (
        pytest.param(False, [("-l",)], id="no-perl"),
        pytest.param(True, [("-l",), ("-e", CPAN._INC_PROBE)], id="plain-inc"),
    ),
)
def test_installed_lists_once_without_symlinked_inc(
    tmp_path, monkeypatch, sibling_perl, expected_calls
):
    """A single `cpan -l` runs when no `@INC` entry is a symlink, and the probe is
    skipped when no `perl` sits beside `cpan` to ask."""
    if sibling_perl:
        (tmp_path / "perl").touch()
    site = tmp_path / "site"
    site.mkdir()

    manager = CPAN()
    manager.__dict__["cli_path"] = tmp_path / "cpan"
    calls = fake_cpan(
        monkeypatch, manager, inc=(str(site),), listings=("Try::Tiny\t0.31",)
    )

    assert [package.id for package in manager.installed] == ["Try::Tiny"]
    assert [args for args, _ in calls] == expected_calls


def test_outdated_ignores_index_refresh_lines(stub_run_cli):
    """The progress lines `CPAN::FTP` prints while it refreshes its index are not
    packages."""
    manager = CPAN()
    stub_run_cli(
        manager,
        "Fetching with HTTP::Tiny:\n"
        "http://www.cpan.org/authors/01mailrc.txt.gz\n"
        "Fetching with HTTP::Tiny:\n"
        "http://www.cpan.org/modules/02packages.details.txt.gz\n"
        "Module Name                                Local    CPAN\n"
        "-------------------------------------------------------------------------\n"
        "App::Cpan                                 1.6780  1.6790\n"
        "Archive::Tar                              3.0200  3.1200\n",
    )

    assert [
        (package.id, str(package.installed_version), str(package.latest_version))
        for package in manager.outdated
    ] == [
        ("App::Cpan", "1.6780", "1.6790"),
        ("Archive::Tar", "3.0200", "3.1200"),
    ]
