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
"""Perl CPAN listing tests, and the local::lib rule.

Where cpan installs to a local::lib directory by default, `cpan -u` installs a
newer copy of each outdated module of the system there. `outdated` and
`upgrade --all` then keep the modules with a file in that directory.

`run_cli` is stubbed, so these tests never invoke `cpan` or `perl`. The
directories they list are real, since the manager tells a symlinked `@INC`
entry apart, and finds the modules of a local::lib directory, through the
filesystem.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from extra_platforms import is_any_windows

from meta_package_manager.managers.cpan import CPAN
from meta_package_manager.version import parse_version

PATCH_ACCESS = "meta_package_manager.managers.cpan.os.access"
PATCH_ROOT = "meta_package_manager.manager._running_as_root"

ARCHNAME = "aarch64-linux-thread-multi"
PERL_VERSION = "5.44.0"

OUTDATED = (
    "Module Name                                Local    CPAN\n"
    "-------------------------------------------------------------------------\n"
    "App::Cpan                                 1.6780  1.6790\n"
    "Cairo                                     1.1090  1.1100\n"
    "local::lib                                2.0000  2.0001\n"
)
"""A `cpan -O` listing with a core module and two modules of a local::lib directory."""


def fake_cpan(monkeypatch, manager, inc, listings):
    """Answer the `@INC` probe with `inc`, and each `cpan -l` with `listings`.

    Each `cpan -l` run gets the next of `listings`. Returns the `(args, kwargs)` of
    every call.
    """
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
    """Modules in a symlinked `@INC` directory come from a second `cpan -l`.

    It never replaces a row of the first.
    """
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
    """A single `cpan -l` runs when no `@INC` entry is a symlink.

    The probe is skipped when no `perl` sits beside `cpan` to ask.
    """
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
    """The progress lines of `CPAN::FTP` index refreshes are not packages."""
    manager = CPAN()
    # A Perl that installs to its own site directory keeps the whole listing.
    manager.__dict__["user_install_dir"] = None
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


@pytest.fixture
def new_cpan(monkeypatch, tmp_path):
    """Build a new `cpan` manager whose commands answer from a table.

    The table maps the first argument of a call (`-MConfig` for the probe of the
    Perl configuration, `-O`) to its output. A `perl` sits beside `cpan`. The
    builder returns the manager and the list of the `(args, kwargs)` of each
    `run_cli` call.
    """
    monkeypatch.delenv("PERL5LIB", raising=False)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "perl").touch()

    def build(answers):
        manager = CPAN()
        # A new instance takes a stand-in path, so the tests never run the
        # `cpan` of the host.
        manager.__dict__["cli_path"] = bin_dir / "cpan"
        calls = []

        def run_cli(*args, **kwargs):
            calls.append((args, kwargs))
            return answers.get(args[0], "")

        monkeypatch.setattr(manager, "run_cli", run_cli)
        return manager, calls

    return build


def perl_config(site_lib):
    """The output of the probe of the Perl configuration, for `site_lib`."""
    return f"{site_lib}\n{PERL_VERSION}\n{ARCHNAME}\n"


def local_lib(root, *module_files):
    """Create the local::lib directory `root`, with each file of `module_files`.

    Each file is a path relative to `lib/perl5`.
    """
    for module_file in module_files:
        path = root / "lib" / "perl5" / module_file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    return root


def _verbs(calls):
    """The first argument of each recorded `run_cli` call."""
    return [args[0] for args, _ in calls]


def test_outdated_keeps_the_modules_of_the_local_lib_directory(
    new_cpan, monkeypatch, tmp_path
):
    """A core module leaves the listing, the modules of the local::lib dir stay.

    `cpan -O` reads the versions of that directory first.
    """
    user_dir = local_lib(
        tmp_path / "perl5",
        "local/lib.pm",
        f"{ARCHNAME}/Cairo.pm",
        f"{PERL_VERSION}/{ARCHNAME}/Cairo/Surface.pm",
    )
    monkeypatch.setenv("PERL_MM_OPT", f"INSTALL_BASE={user_dir}")
    manager, calls = new_cpan({
        "-MConfig": perl_config(tmp_path / "site"),
        "-O": OUTDATED,
    })
    packages = list(manager.refiltered_outdated)

    assert [
        (p.id, str(p.installed_version), str(p.latest_version)) for p in packages
    ] == [("Cairo", "1.1090", "1.1100"), ("local::lib", "2.0000", "2.0001")]
    assert manager._packages_in(user_dir) == {"Cairo", "Cairo::Surface", "local::lib"}
    assert _verbs(calls) == ["-MConfig", "-O"]
    _, outdated_kwargs = calls[1]
    assert outdated_kwargs["override_extra_env"] == {
        "PERL_MM_USE_DEFAULT": "1",
        "PERL5LIB": str(user_dir / "lib" / "perl5"),
    }


def test_outdated_runs_no_listing_without_a_module_in_the_local_lib_directory(
    new_cpan, monkeypatch, tmp_path
):
    """With no module in the local::lib directory, `cpan -O` never runs."""
    monkeypatch.setenv("PERL_MM_OPT", f"INSTALL_BASE={tmp_path / 'perl5'}")
    manager, calls = new_cpan({"-O": OUTDATED})
    assert list(manager.refiltered_outdated) == []
    assert calls == []


def test_outdated_lists_every_module_without_the_local_lib_default(new_cpan, tmp_path):
    """A Perl installing to its own site directory keeps the whole listing."""
    site = tmp_path / "site"
    site.mkdir()
    manager, calls = new_cpan({"-MConfig": perl_config(site), "-O": OUTDATED})
    with patch(PATCH_ACCESS, return_value=True):
        assert [p.id for p in manager.refiltered_outdated] == [
            "App::Cpan",
            "Cairo",
            "local::lib",
        ]
    assert _verbs(calls) == ["-MConfig", "-O"]
    assert calls[1][1]["override_extra_env"] is None


@pytest.mark.parametrize(
    ("perl_mm_opt", "expected"),
    (
        pytest.param(
            "INSTALL_BASE=/home/user/perl5", Path("/home/user/perl5"), id="local-lib"
        ),
        pytest.param(
            'INSTALL_BASE="/home/user/my perl"',
            Path("/home/user/my perl"),
            id="double-quoted",
        ),
        pytest.param(
            "INSTALLDIRS=site INSTALL_BASE=/opt/perl5",
            Path("/opt/perl5"),
            id="among-other-arguments",
        ),
        pytest.param("INSTALLDIRS=site", None, id="no-install-base"),
    ),
)
@pytest.mark.parametrize("source", ("environ", "extra_env"))
def test_install_base_decides(
    new_cpan, monkeypatch, tmp_path, perl_mm_opt, expected, source
):
    """An `INSTALL_BASE` in `PERL_MM_OPT` names the local::lib directory."""
    site = tmp_path / "site"
    site.mkdir()
    manager, _ = new_cpan({"-MConfig": perl_config(site)})
    if source == "environ":
        monkeypatch.setenv("PERL_MM_OPT", perl_mm_opt)
    else:
        monkeypatch.setattr(manager, "extra_env", {"PERL_MM_OPT": perl_mm_opt})
    # A writable site directory keeps the fallback out of these cases.
    with patch(PATCH_ACCESS, return_value=True):
        assert manager.user_install_dir == expected


@pytest.mark.parametrize(
    ("writable", "local_lib_root", "expected"),
    (
        pytest.param(False, None, Path.home() / "perl5", id="not-writable"),
        pytest.param(
            False,
            os.pathsep.join(("/opt/perl5", "/srv/perl5")),
            Path("/opt/perl5"),
            id="local-lib-root",
        ),
        pytest.param(True, None, None, id="writable"),
    ),
)
def test_read_only_site_directory_falls_back_to_local_lib(
    new_cpan, monkeypatch, tmp_path, writable, local_lib_root, expected
):
    """Without `INSTALL_BASE`, a read-only site directory sends cpan to local::lib."""
    site = tmp_path / "site"
    site.mkdir()
    if local_lib_root:
        monkeypatch.setenv("PERL_LOCAL_LIB_ROOT", local_lib_root)
    manager, _ = new_cpan({"-MConfig": perl_config(site)})
    with patch(PATCH_ACCESS, return_value=writable):
        assert manager.user_install_dir == expected


@pytest.mark.parametrize(
    "answers",
    (
        pytest.param({"-MConfig": perl_config("/missing/site")}, id="missing-site"),
        pytest.param({"-MConfig": ""}, id="empty-probe"),
        pytest.param({}, id="no-answer"),
    ),
)
def test_unreadable_site_directory_keeps_the_rule_off(new_cpan, answers):
    """A site directory the probe cannot name, or that does not exist, keeps cpan."""
    manager, _ = new_cpan(answers)
    with patch(PATCH_ACCESS, return_value=False):
        assert manager.user_install_dir is None


def test_no_sibling_perl_keeps_the_rule_off(new_cpan, tmp_path):
    """Without a `perl` beside `cpan`, no probe runs and the rule stays off."""
    manager, calls = new_cpan({"-MConfig": perl_config(tmp_path)})
    manager.__dict__["cli_path"] = tmp_path / "elsewhere" / "cpan"
    with patch(PATCH_ACCESS, return_value=False):
        assert manager.user_install_dir is None
    assert calls == []


def test_upgrade_all_upgrades_the_kept_modules_one_by_one(
    new_cpan, monkeypatch, tmp_path
):
    """A full upgrade runs `cpan -i` on each module of the local::lib dir alone."""
    user_dir = local_lib(tmp_path / "perl5", "local/lib.pm")
    monkeypatch.setenv("PERL_MM_OPT", f"INSTALL_BASE={user_dir}")
    manager, _ = new_cpan({
        "-MConfig": perl_config(tmp_path / "site"),
        "-O": OUTDATED,
    })
    commands = []

    def run(*args, **kwargs):
        commands.append(args[0])
        return ""

    monkeypatch.setattr(manager, "run", run)
    manager.upgrade()
    assert commands == [(str(manager.cli_path), "-i", "local::lib")]


def test_upgrade_all_runs_cpan_u_on_its_own_site_directory(
    new_cpan, monkeypatch, tmp_path
):
    """The bare `cpan -u` stays for a Perl installing to its own site directory."""
    site = tmp_path / "site"
    site.mkdir()
    manager, _ = new_cpan({"-MConfig": perl_config(site), "-O": OUTDATED})
    commands = []

    def run(*args, **kwargs):
        commands.append(args[0])
        return ""

    monkeypatch.setattr(manager, "run", run)
    with patch(PATCH_ACCESS, return_value=True):
        manager.upgrade()
    assert commands == [(str(manager.cli_path), "-u")]


def test_sudo_turns_the_rule_off(new_cpan, monkeypatch, tmp_path):
    """Under `mpm --sudo`, root runs `cpan -u`: no probe runs as the user."""
    monkeypatch.setenv("PERL_MM_OPT", f"INSTALL_BASE={tmp_path / 'perl5'}")
    manager, calls = new_cpan({"-MConfig": perl_config(tmp_path)})
    monkeypatch.setattr(manager, "sudo", True)
    with patch(PATCH_ROOT, return_value=False):
        assert manager.user_install_dir is None
    assert calls == []


def test_root_keeps_the_rule(new_cpan, monkeypatch, tmp_path):
    """Run as root, `mpm --sudo` escalates nothing: the rule reads root's defaults."""
    monkeypatch.setenv("PERL_MM_OPT", f"INSTALL_BASE={tmp_path / 'perl5'}")
    manager, _ = new_cpan({})
    monkeypatch.setattr(manager, "sudo", True)
    with patch(PATCH_ROOT, return_value=True):
        assert manager.user_install_dir == tmp_path / "perl5"


@pytest.mark.parametrize(
    ("shebang", "beside", "expected"),
    (
        pytest.param("#!{perl}\n", False, "shebang", id="shebang-apart"),
        pytest.param("#!{perl} -w\n", False, "shebang", id="shebang-with-switch"),
        pytest.param("#!/usr/bin/env perl\n", True, "beside", id="env-shebang"),
        pytest.param("#!{missing}\n", True, "beside", id="missing-interpreter"),
        pytest.param("", True, "beside", id="no-shebang"),
        pytest.param("#!/usr/bin/env perl\n", False, None, id="no-perl-at-all"),
    ),
)
def test_perl_runs_cpan(tmp_path, shebang, beside, expected):
    """The `perl` of `cpan` is the shebang's, else the one beside the script.

    Arch Linux installs `cpan` to `/usr/bin/core_perl`, apart from `/usr/bin/perl`.
    """
    perl = tmp_path / "bin" / "perl"
    perl.parent.mkdir()
    perl.touch()
    script = tmp_path / "core_perl" / "cpan"
    script.parent.mkdir()
    script.write_text(
        shebang.format(perl=perl, missing=tmp_path / "perl"), encoding="UTF-8"
    )
    sibling = script.parent / "perl"
    if beside:
        sibling.touch()

    manager = CPAN()
    manager.__dict__["cli_path"] = script
    assert manager._perl() == {"shebang": perl, "beside": sibling, None: None}[expected]


@pytest.mark.parametrize(
    ("missing", "unavailable"),
    (
        pytest.param("auto_commit\nbuild_cache\nurllist\n", True, id="no-config"),
        pytest.param("urllist\n", True, id="one-setting-missing"),
        pytest.param("pushy_https\n", False, id="pushy-https-alone"),
        pytest.param("", False, id="configured"),
        pytest.param("Can't locate CPAN.pm in @INC.\n", False, id="unrelated-output"),
    ),
)
def test_unconfigured_cpan_pm_makes_cpan_unavailable(new_cpan, missing, unavailable):
    """Each `cpan` command would start the first-run setup of an unconfigured CPAN.pm.

    The probe asks the `perl` of `cpan`, never `cpan` itself.
    """
    manager, calls = new_cpan({"-MCPAN": missing})
    manager.__dict__["executable"] = True
    manager.__dict__["version"] = parse_version("2.38")
    reason = manager.unavailable_reason
    assert (reason is not None) is unavailable
    if unavailable:
        assert reason.startswith("CPAN.pm has no configuration")
    assert [kwargs["override_cli_path"] for _, kwargs in calls] == [manager._perl()]


def test_availability_never_runs_cpan(monkeypatch, tmp_path):
    """Neither the version probe nor the configuration check runs `cpan` itself.

    Each option of `cpan` but `-h` and `-j` loads the configuration of CPAN.pm,
    whose first-run setup would start in a home where `cpan` never ran.
    """
    perl = tmp_path / "perl"
    perl.touch()
    manager = CPAN()
    manager.__dict__["cli_path"] = tmp_path / "cpan"
    manager.__dict__["executable"] = True
    monkeypatch.setattr(manager, "which", lambda name: perl if name == "perl" else None)
    cli_paths = []

    def run_cli(*args, **kwargs):
        cli_paths.append(kwargs.get("override_cli_path"))
        if args[0] == CPAN.version_cli_options:
            return "CPAN.pm version 2.38\n"
        return "auto_commit\nurllist\n"

    monkeypatch.setattr(manager, "run_cli", run_cli)
    assert manager.available is False
    assert str(manager.version) == "2.38"
    assert cli_paths == [perl, perl]
