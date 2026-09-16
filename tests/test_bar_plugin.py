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

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
from collections import Counter
from itertools import product
from typing import ClassVar, cast

import pytest
from boltons.iterutils import flatten
from boltons.strutils import strip_ansi
from click_extra.color import COLOR_ENVVARS
from click_extra.execution import args_cleanup
from extra_platforms.pytest import unless_macos

from meta_package_manager import __version__, bar_plugin
from meta_package_manager.bar_plugin_renderer import (
    DARK_MENU_NEW_COLOR,
    LIGHT_MENU_NEW_COLOR,
    LIGHT_MENU_OLD_COLOR,
    MAX_VERSION_WIDTH,
    VERSION_ELLIPSIS,
    VERSION_PREFIX_COLOR,
    BarPluginRenderer,
    elide_versions,
)
from meta_package_manager.version import parse_version

TYPE_CHECKING = False
if TYPE_CHECKING:
    from click_extra.envvar import TEnvVars


@pytest.mark.parametrize(
    ("param_string", "results"),
    (
        ("font=Menlo", "font=Menlo"),
        ("font=Menlo size=12", "font=Menlo size=12"),
        ("      font=Menlo      ", "font=Menlo"),
        ("      font   =   Menlo      ", "font=Menlo"),
        ("      font   =   Menlo  Menlo    ", "font=Menlo"),
        ("", ""),
        ("        ", ""),
        ("  font=      ", ""),
        ("  font      ", ""),
        ("   = foo ", ""),
        ("=", ""),
        ("==", ""),
        ("   =  =    ", ""),
        ("random=", ""),
        ("RANDOM=", ""),
        ("Font=", ""),
        ("font=Menlo font=Menlo", "font=Menlo"),
        ("size=10 size=20", "size=20"),
        ("font='Comic Sans MS'", "font='Comic Sans MS'"),
        ('font="Comic Sans MS"', 'font="Comic Sans MS"'),
    ),
)
def test_normalize_params(param_string, results):
    assert bar_plugin.MPMPlugin.normalize_params(param_string) == results


def test_check_mpm_missing_binary():
    """A probe whose binary does not exist must report the error, not crash.

    Regression test for the `UnboundLocalError` on the `FileNotFoundError`
    path of `check_mpm()`, where `process` is never assigned.
    """
    runnable, up_to_date, version, error, release = bar_plugin.MPMPlugin().check_mpm(
        ("/nonexistent/mpm-binary",),
    )
    assert runnable is False
    assert up_to_date is False
    assert version is None
    assert release is None
    assert isinstance(error, FileNotFoundError)


def test_check_mpm_keeps_the_release_suffix():
    """Both readings of one string: the tuple compares, the release is verbatim.

    Spawned through the running interpreter rather than a shell, so the probe
    is the same on Windows. `check_mpm` appends its own `--no-color
    --version`, which the script ignores.
    """
    runnable, up_to_date, version, error, release = bar_plugin.MPMPlugin().check_mpm(
        (sys.executable, "-c", 'print("mpm, version 8.0.0.dev0+abc1234")'),
    )
    assert runnable is True
    assert up_to_date is True
    assert version == (8, 0, 0)
    assert release == "8.0.0.dev0+abc1234"
    assert not error


def test_search_mpm_stops_at_home(monkeypatch, tmp_path):
    """The venv walk stops at Home, so a lockfile sitting in a shared parent
    above it is never mistaken for the plugin's own project."""
    home = tmp_path / "home"
    project = home / "project"
    project.mkdir(parents=True)
    (project / "uv.lock").touch()
    (tmp_path / "uv.lock").touch()

    monkeypatch.setattr(bar_plugin, "__file__", str(project / "bar_plugin.py"))
    monkeypatch.setattr(bar_plugin.Path, "home", classmethod(lambda cls: home))

    candidates = list(bar_plugin.MPMPlugin().search_mpm())

    def uv_candidate(folder):
        return ("uv", "run", "--frozen", "--project", str(folder), "mpm")

    assert uv_candidate(project) in candidates
    assert uv_candidate(tmp_path) not in candidates


@pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="python -P was added in 3.11",
)
def test_mpm_cli_ignores_the_spawn_directory(tmp_path):
    """A menu action imports the installed `mpm`, wherever it is spawned from.

    `-m` prepends the working directory to `sys.path`, so an action started
    from a source checkout used to import that tree with the dependencies the
    installed version pinned.
    """
    decoy = tmp_path / "meta_package_manager"
    decoy.mkdir()
    (decoy / "__init__.py").write_text(
        'raise SystemExit("decoy imported")',
        encoding="UTF-8",
    )

    process = subprocess.run(
        (*BarPluginRenderer().mpm_cli, "--version"),
        capture_output=True,
        cwd=tmp_path,
        encoding="UTF-8",
        check=False,
    )

    assert "decoy imported" not in process.stderr
    assert process.returncode == 0
    assert "mpm, version" in process.stdout


def test_search_mpm_resolves_a_symlinked_plugin(monkeypatch, tmp_path):
    """The venv walk follows the symlink both hosts are installed through.

    A bar app imports this file from its own plugin folder, so an unresolved
    `__file__` walks that folder and finds nothing, leaving the plugin to drive
    whichever other `mpm` the system answers with.
    """
    home = tmp_path / "home"
    project = home / "project"
    package = project / "meta_package_manager"
    package.mkdir(parents=True)
    (project / "uv.lock").touch()
    target = package / "bar_plugin.py"
    target.touch()

    plugin_folder = home / ".swiftbar"
    plugin_folder.mkdir()
    link = plugin_folder / "meta_package_manager.7h.py"
    link.symlink_to(target)

    monkeypatch.setattr(bar_plugin, "__file__", str(link))
    monkeypatch.setattr(bar_plugin.Path, "home", classmethod(lambda cls: home))

    candidates = list(bar_plugin.MPMPlugin().search_mpm())

    assert ("uv", "run", "--frozen", "--project", str(project), "mpm") in candidates


def _pin_plugin_env(
    monkeypatch, align_columns: bool, os_appearance: str | None = None
) -> None:
    """Pin the plugin environment variables so host values never leak in.

    `os_appearance` sets SwiftBar's `OS_APPEARANCE` variable when provided; it
    is deleted otherwise, so the host appearance never reaches the renderer.
    """
    monkeypatch.setenv("VAR_ALIGN_COLUMNS", str(align_columns))
    for var in (
        "SWIFTBAR",
        "VAR_DEFAULT_FONT",
        "VAR_ALWAYS_VISIBLE",
        "VAR_MAX_VERSION_WIDTH",
        "VAR_MONOSPACE_FONT",
        "VAR_MPM_OPTIONS",
        "VAR_GROUP_BY_MANAGER",
    ):
        monkeypatch.delenv(var, raising=False)
    if os_appearance is None:
        monkeypatch.delenv("OS_APPEARANCE", raising=False)
    else:
        monkeypatch.setenv("OS_APPEARANCE", os_appearance)


def _outdated_fixture(errors: list[str] | None = None) -> dict:
    """Deterministic outdated data in the shape `mpm outdated` produces.

    Version pairs share a common prefix so all three diff segments (gray
    prefix, red installed suffix, green latest suffix) are exercised. The
    second package carries no upgrade CLI, like a manager without a
    single-package upgrade command.

    Versions are parsed rather than left as strings, which is what `mpm
    outdated` puts in this payload: a renderer helper reaching for a string
    method fails on the real type alone.
    """
    return {
        "fakemanager": {
            "id": "fakemanager",
            "name": "Fake Manager",
            "packages": [
                {
                    "id": "pkg-one",
                    "name": "pkg-one",
                    "installed_version": parse_version("8.2.1"),
                    "latest_version": parse_version("8.3.0"),
                    "upgrade_cli": "shell=/bin/fake param1=upgrade param2=pkg-one",
                },
                {
                    "id": "another-long-package",
                    "name": "another-long-package",
                    "installed_version": parse_version("2.0.0"),
                    "latest_version": parse_version("2.0.1"),
                    "upgrade_cli": None,
                },
            ],
            "errors": errors or [],
            "upgrade_all_cli": "shell=/bin/fake param1=upgrade param2=--all",
        },
    }


def test_print_honors_a_color_opt_out_off_the_main_thread(
    monkeypatch, capsys, fake_pool
):
    """An explicit `--no-color` strips the plugin output wherever it is rendered.

    Only the automatic color state is forced on (see
    `test_plugin_output_keeps_ansi`). The opt-out comes from the color the
    invocation published for every thread, so it holds on a worker thread too,
    where the thread-local command context is absent.
    """
    for var in (*COLOR_ENVVARS, "TERM"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("click_extra.color._invocation_color", False)
    worker = threading.Thread(
        target=BarPluginRenderer().print, args=(_outdated_fixture(),)
    )
    worker.start()
    worker.join()
    output = capsys.readouterr().out
    assert "pkg-one" in output
    assert "\x1b[" not in output


@pytest.mark.parametrize("align_columns", (True, False))
@pytest.mark.parametrize(
    ("os_appearance", "present", "absent"),
    (
        # No OS_APPEARANCE (dark-agnostic consumer like Xbar): keep the system
        # red/green (SGR 31/32); no palette override leaks in.
        (None, ("\x1b[31m", "\x1b[32m"), (f"\x1b[38;5;{DARK_MENU_NEW_COLOR}m",)),
        # Light menu: both suffixes darkened; no system red/green survives.
        (
            "Light",
            (
                f"\x1b[38;5;{LIGHT_MENU_OLD_COLOR}m",
                f"\x1b[38;5;{LIGHT_MENU_NEW_COLOR}m",
            ),
            ("\x1b[31m", "\x1b[32m"),
        ),
        # Dark menu: green brightened, red kept as the system red.
        (
            "Dark",
            (f"\x1b[38;5;{DARK_MENU_NEW_COLOR}m", "\x1b[31m"),
            ("\x1b[32m",),
        ),
    ),
)
def test_renderer_version_diff_colors_by_appearance(
    monkeypatch, align_columns, os_appearance, present, absent
):
    """Package lines carry the appearance-appropriate version-diff colors with
    `ansi=true`; the prefix gray is constant and non-package lines stay free of
    escape codes."""
    _pin_plugin_env(monkeypatch, align_columns, os_appearance=os_appearance)
    output = BarPluginRenderer().render(_outdated_fixture())

    package_lines = [line for line in output.splitlines() if "ansi=true" in line]
    # 2 packages, each rendered twice (terminal and alternate menu entries).
    assert len(package_lines) == 4
    for line in package_lines:
        assert f"\x1b[38;5;{VERSION_PREFIX_COLOR}m" in line
        assert "\x1b[0m" in line
        for code in present:
            assert code in line
        for code in absent:
            assert code not in line

    for line in output.splitlines():
        if "ansi=true" not in line:
            assert "\x1b[" not in line


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    (
        # Homebrew's `version,revision` cask pair, the 50-character row that
        # blanked its own target version in a real menu.
        pytest.param(
            "1.49585.0,41ad1dff5275eedc8af25989f59f33c5efe14063",
            "1.52386.4,5078b3dcabffbffb717315a5f9a0e552c9ca54d6",
            ("1.49585.0,41ad1df…", "1.52386.4,5078b3d…"),
            id="cask-revision-pair",
        ),
        # A Neovim plugin pinned by commit: 40 characters diverging at the first.
        pytest.param(
            "016802de402556da54c36bd7359b441266b01cdd",
            "5cb0114e6242625db56dd6440e945ed1ece10bc7",
            ("016802de402556da5…", "5cb0114e6242625db…"),
            id="commit-sha",
        ),
        # A Julia build triple, where the platform tail is the shared noise.
        pytest.param(
            "1.10.11+0.aarch64.apple.darwin14",
            "1.12.6+0.aarch64.apple.darwin14",
            ("1.10.11+0.aarch64…", "1.12.6+0.aarch64.…"),
            id="build-triple",
        ),
        # Both sides over the cap. They must come back cut the same way, or the
        # column stops lining up: the per-version decision this replaced left
        # one head-elided beside one tail-cut.
        pytest.param(
            "5.0.0~beta1-0ubuntu7",
            "5.0.2-0ubuntu1~26.04.1",
            ("5.0.0~beta1-0ubun…", "5.0.2-0ubuntu1~26…"),
            id="both-sides-capped",
        ),
        # A separator-free pair long enough to fill the budget on its own, whose
        # divergence sits past the cap: the tail is what has to show.
        pytest.param(
            "a" * 20 + "X1",
            "a" * 20 + "X2",
            ("…" + "a" * 15 + "X1", "…" + "a" * 15 + "X2"),
            id="no-separator-late-divergence",
        ),
        # A rebuild differing only in its last character. Cutting the tail would
        # render both sides alike, so the shared head is what gives way.
        pytest.param(
            "2.6.0-2.suse1699.10",
            "2.6.0-2.suse1699.11",
            ("2.6.0-2.suse16….10", "2.6.0-2.suse16….11"),
            id="late-divergence",
        ),
        # The longest version a person reads in the survey, and a plain pair:
        # both sit under the cap and come back untouched.
        pytest.param(
            "152.0.7977.82-1.1",
            "152.0.7977.82-1.2",
            ("152.0.7977.82-1.1", "152.0.7977.82-1.2"),
            id="longest-untouched",
        ),
        pytest.param("0.12.11", "0.12.13", ("0.12.11", "0.12.13"), id="plain-semver"),
    ),
)
def test_elide_versions(old, new, expected):
    """A capped pair stays within the cap, and stays distinguishable."""
    elided = elide_versions(old, new, MAX_VERSION_WIDTH)
    assert elided == expected
    assert max(len(version) for version in elided) <= MAX_VERSION_WIDTH
    assert elided[0] != elided[1]


def test_elide_versions_keeps_the_diff_boundary():
    """The `…` lands where the gray prefix hands over to the colored suffix, so
    the elision and {func}`diff_versions` agree on one split point."""
    old, new = elide_versions("1.0.0+build.20260101", "1.0.0+build.20260102", 16)
    assert (old, new) == ("1.0.0+\u2026.20260101", "1.0.0+\u2026.20260102")
    # The whole diverging token survives on both sides, so the eye lands on the
    # one character that differs.
    assert old.endswith(".20260101")
    assert new.endswith(".20260102")


@pytest.mark.parametrize("swiftbar", (True, False))
def test_renderer_caps_version_cells(monkeypatch, swiftbar):
    """An over-long version is elided in the menu line, and SwiftBar alone gets
    the tooltip holding what was dropped."""
    _pin_plugin_env(monkeypatch, align_columns=True)
    if swiftbar:
        monkeypatch.setenv("SWIFTBAR", "1")
    full_old = "1.49585.0,41ad1dff5275eedc8af25989f59f33c5efe14063"
    full_new = "1.52386.4,5078b3dcabffbffb717315a5f9a0e552c9ca54d6"
    fixture = _outdated_fixture()
    fixture["fakemanager"]["packages"][0]["installed_version"] = full_old
    fixture["fakemanager"]["packages"][0]["latest_version"] = full_new

    output = BarPluginRenderer().render(fixture)

    lines = [line for line in strip_ansi(output).splitlines() if "ansi=true" in line]
    assert lines
    # Widest package name of the fixture, its spacer, two capped version cells
    # and the arrow between them.
    widest = len("another-long-package") + 2 + MAX_VERSION_WIDTH + 3 + MAX_VERSION_WIDTH
    for line in lines:
        label = line.split(" | ")[0]
        assert full_old not in label
        assert len(label) <= widest
    capped = [line for line in lines if VERSION_ELLIPSIS in line.split(" | ")[0]]
    # The capped package, rendered as a terminal entry and an alternate one.
    assert len(capped) == 2
    for line in capped:
        assert ("1.49585.0,41ad1df…" in line) and ("1.52386.4,5078b3d…" in line)
        expected_tooltip = f'tooltip="{full_old} → {full_new}"'
        assert (expected_tooltip in line) is swiftbar
    # The pair already under the cap carries no tooltip.
    for line in set(lines) - set(capped):
        assert "tooltip=" not in line


@pytest.mark.parametrize(
    ("value", "capped"),
    (("0", False), ("1", False), ("24", True), ("not-a-number", True)),
)
def test_renderer_version_cap_is_configurable(monkeypatch, value, capped):
    """`VAR_MAX_VERSION_WIDTH` overrides the cap; a width leaving no room for
    the ellipsis turns it off, and a value that is not a number falls back to
    the default."""
    _pin_plugin_env(monkeypatch, align_columns=True)
    monkeypatch.setenv("VAR_MAX_VERSION_WIDTH", value)
    fixture = _outdated_fixture()
    fixture["fakemanager"]["packages"][0]["installed_version"] = "1.0." + "a" * 30
    fixture["fakemanager"]["packages"][0]["latest_version"] = "1.0." + "b" * 30

    output = strip_ansi(BarPluginRenderer().render(fixture))
    assert (VERSION_ELLIPSIS in output) is capped


def test_renderer_table_alignment_survives_ansi(monkeypatch):
    """Column alignment is computed on visible widths, not raw string lengths."""
    _pin_plugin_env(monkeypatch, align_columns=True)
    output = BarPluginRenderer().render(_outdated_fixture())

    arrow_lines = [line for line in strip_ansi(output).splitlines() if "→" in line]
    assert len(arrow_lines) == 4
    assert len({line.index("→") for line in arrow_lines}) == 1
    assert len({line.index(" | ") for line in arrow_lines}) == 1


def test_renderer_elides_long_payload_versions(monkeypatch):
    """A version pair past the cap is elided, as the payload's own type.

    Regression test for the `TypeError` that took the whole menu down on any
    package whose versions ran past {data}`MAX_VERSION_WIDTH`: `mpm outdated`
    fills this payload with `TokenizedString` versions, which answer `len()`
    but cannot be sliced, and elision slices.
    """
    _pin_plugin_env(monkeypatch, align_columns=True)
    payload = _outdated_fixture()
    payload["fakemanager"]["packages"][0] |= {
        "installed_version": parse_version("1:4.16.0-2+really2.41.3-3ubuntu2"),
        "latest_version": parse_version("1:4.16.0-2+really2.41.3-3ubuntu2.2"),
    }

    rendered = strip_ansi(BarPluginRenderer().render(payload))

    elided = [token for token in rendered.split() if VERSION_ELLIPSIS in token]
    assert elided
    for token in elided:
        assert len(token) <= MAX_VERSION_WIDTH


def test_renderer_sanitizes_error_lines(monkeypatch):
    """ANSI codes captured from a manager's output are stripped from error
    lines, which are marked `ansi=false` and would render them as raw text."""
    _pin_plugin_env(monkeypatch, align_columns=True)
    output = BarPluginRenderer().render(
        _outdated_fixture(errors=["\x1b[31mboom\x1b[0m went wrong"]),
    )

    error_lines = [line for line in output.splitlines() if "boom" in line]
    assert error_lines
    for line in error_lines:
        assert "ansi=false" in line
        assert "\x1b[" not in line


@pytest.mark.parametrize(
    ("is_swiftbar", "group_by_manager", "align_columns", "outdated", "expected"),
    (
        # Xbar renders neither parameter, so the count stays in the label.
        (False, False, True, True, "fakemanager - 2 packages | font=Menlo size=12"),
        (False, True, True, True, "fakemanager - 2 packages | font=Menlo size=12"),
        (False, False, False, True, "2 outdated Fake Manager packages |"),
        # SwiftBar moves the count to a native badge.
        (True, False, True, True, "fakemanager | font=Menlo size=12 badge=2"),
        (True, False, False, True, "Fake Manager | badge=2"),
        # And folds the section into an accordion once the grouped layout gave
        # it the children to fold.
        (True, True, True, True, "fakemanager | font=Menlo size=12 badge=2 fold=true"),
        # A zero count earns no badge, the section being proof enough that the
        # manager was queried.
        (True, False, True, False, "fakemanager | font=Menlo size=12"),
        (True, True, True, False, "fakemanager | font=Menlo size=12 fold=true"),
    ),
)
def test_renderer_section_header(
    monkeypatch, is_swiftbar, group_by_manager, align_columns, outdated, expected
):
    """The section header carries an actionable count badge and an accordion
    toggle on SwiftBar, and the labelled count everywhere else."""
    _pin_plugin_env(monkeypatch, align_columns=align_columns)
    monkeypatch.setenv("VAR_GROUP_BY_MANAGER", str(group_by_manager))
    if is_swiftbar:
        monkeypatch.setenv("SWIFTBAR", "1")

    data = _outdated_fixture()
    if not outdated:
        data["fakemanager"]["packages"] = []

    # The menu bar line and the section separator precede the header.
    assert BarPluginRenderer().render(data).splitlines()[2] == expected


@pytest.mark.parametrize(
    ("hide", "errors", "renders"),
    (
        # Nothing to report, but the icon is kept by default.
        (False, [], True),
        (True, [], False),
        # An error is a report of its own: hiding it would bury a broken manager.
        (True, ["boom"], True),
    ),
)
def test_renderer_hides_when_up_to_date(monkeypatch, hide, errors, renders):
    """An empty rendering is what makes the host drop the menu bar icon, so it
    is produced only when asked for and only when there is nothing to say."""
    _pin_plugin_env(monkeypatch, align_columns=True)
    monkeypatch.setenv("VAR_ALWAYS_VISIBLE", str(not hide))

    output = BarPluginRenderer().render({
        "fakemanager": {
            "id": "fakemanager",
            "name": "Fake Manager",
            "packages": [],
            "errors": errors,
        },
    })

    # Whitespace would not do: the host keys the icon on a strictly empty output.
    assert bool(output) is renders


@pytest.mark.parametrize(
    ("hide", "reports_error"),
    (
        (False, True),
        (True, False),
    ),
)
def test_plugin_empty_mpm_output(monkeypatch, capsys, hide, reports_error):
    """An `mpm` producing nothing is a failure to report, unless the user asked
    for the icon to vanish while everything is up to date."""
    monkeypatch.delenv("SWIFTBAR", raising=False)
    monkeypatch.setenv("VAR_ALWAYS_VISIBLE", str(not hide))
    monkeypatch.setattr(
        bar_plugin,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args, 0, stdout="", stderr=""
        ),
    )

    plugin = bar_plugin.MPMPlugin()
    # Short-circuit the search for a runnable mpm: a cached_property reads back
    # from the instance dictionary.
    plugin.__dict__["best_mpm"] = (("mpm",), True, True, (9, 9, 9), None, "9.9.9")
    plugin.print_menu()

    out = capsys.readouterr().out
    assert ("\u2757\ufe0f" in out) is reports_error
    # Producing nothing at all is what makes the host hide the plugin, so not
    # even the About footer may slip out.
    assert bool(out) is reports_error


def test_plugin_options_reach_every_call(monkeypatch):
    """`VAR_MPM_OPTIONS` lands after the plugin's own options and before the
    subcommand on the sync and outdated calls, keeps its case, and never
    reaches the version probe."""
    _pin_plugin_env(monkeypatch, align_columns=True)
    monkeypatch.setenv("VAR_MPM_OPTIONS", "--verbosity INFO --no-cpan")
    calls: list[tuple[str, ...]] = []

    def fake_run(args, **kwargs):
        calls.append(tuple(args))
        return subprocess.CompletedProcess(
            args, 0, stdout="\U0001f4e6\u2713 | dropdown=false", stderr=""
        )

    monkeypatch.setattr(bar_plugin, "run", fake_run)
    plugin = bar_plugin.MPMPlugin()
    plugin.__dict__["best_mpm"] = (
        ("/somewhere/mpm",),
        True,
        True,
        (9, 9, 9),
        None,
        "9.9.9",
    )

    plugin.print_menu()
    assert [args[-1] for args in calls] == ["sync", "--plugin-output"]
    for args, subcommand in zip(calls, ("sync", "outdated")):
        cut = args.index(subcommand)
        assert args[cut - 3 : cut] == ("--verbosity", "INFO", "--no-cpan")
        # The plugin's own verbosity comes first, so the user's wins in click.
        assert args.index("--verbosity") < cut - 3

    calls.clear()
    plugin.check_mpm(("/somewhere/mpm",))
    assert calls == [("/somewhere/mpm", "--no-color", "--version")]


def test_renderer_actions_carry_the_options(monkeypatch):
    """The upgrade commands the menu embeds carry the same options, read from
    the environment the `outdated` call inherits."""
    _pin_plugin_env(monkeypatch, align_columns=True)
    monkeypatch.setenv("VAR_MPM_OPTIONS", "--dry-run")
    assert BarPluginRenderer().mpm_cli[-1] == "--dry-run"


def test_plugin_version_matches_the_package():
    """The `<xbar.version>` header is kept in lockstep with the package by
    bump-my-version, like the GNOME extension's `version-name`."""
    assert bar_plugin.MPMPlugin().plugin_version == __version__


@pytest.mark.parametrize(
    ("swiftbar", "host"),
    (
        (False, "Xbar"),
        (True, "SwiftBar"),
    ),
)
def test_plugin_about_footer(monkeypatch, capsys, swiftbar, host):
    """The footer names both halves of the install and the CLI behind them."""
    if swiftbar:
        monkeypatch.setenv("SWIFTBAR", "true")
        monkeypatch.setenv("SWIFTBAR_VERSION", "2.1.0")
    else:
        monkeypatch.delenv("SWIFTBAR", raising=False)
    monkeypatch.setenv("VAR_ALWAYS_VISIBLE", "true")
    monkeypatch.setattr(
        bar_plugin,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args, 0, stdout="\U0001f4e6\u2713 | dropdown=false", stderr=""
        ),
    )

    plugin = bar_plugin.MPMPlugin()
    plugin.__dict__["best_mpm"] = (
        ("/somewhere/mpm",),
        True,
        True,
        (9, 9, 9),
        None,
        "9.9.9.dev0+abc1234",
    )
    plugin.print_menu()

    out = capsys.readouterr().out
    assert f"--Meta Package Manager ({host} plugin) {plugin.plugin_version}" in out
    # The release as printed, suffix included: the numeric tuple beside it
    # would report this development build as a plain 9.9.9.
    assert "--mpm 9.9.9.dev0+abc1234" in out
    assert "--/somewhere/mpm" in out
    assert f"href={bar_plugin.PLUGIN_DOCS_URL}" in out


def _invocation_matrix(*iterables):
    """Pre-compute a matrix of all possible options for invocation."""
    for args in product(*iterables):
        yield args_cleanup(args)


def _shell_invocation_matrix():
    """Pre-compute a matrix of all possible options used for shell invocation.

    See the list of shell supported by SwiftBar at:
    https://github.com/swiftbar/SwiftBar/commit/366695d594884fe141bc1752ab0f25d2c43334fa

    Returns
    -------
    ```{code-block} python
    (
        ("bash", "-c"),
        ("bash", "--login", "-c"),
        ("/bin/bash", "-c"),
        ("/bin/bash", "--login", "-c"),
        ("zsh", "-c"),
        ("zsh", "--login", "-c"),
        ("/bin/zsh", "-c"),
        ("/bin/zsh", "--login", "-c"),
        ("/usr/bin/env", "bash", "-c"),
        ("/usr/bin/env", "bash", "--login", "-c"),
        ("/usr/bin/env", "/bin/bash", "-c"),
        ("/usr/bin/env", "/bin/bash", "--login", "-c"),
        ("/usr/bin/env", "zsh", "-c"),
        ("/usr/bin/env", "zsh", "--login", "-c"),
        ("/usr/bin/env", "/bin/zsh", "-c"),
        ("/usr/bin/env", "/bin/zsh", "--login", "-c"),
        None,
    )
    ```
    """
    return list(
        _invocation_matrix(
            # Env prefixes.
            (None, "/usr/bin/env"),
            # Naked and full binary paths.
            flatten((bin_id, f"/bin/{bin_id}") for bin_id in ("bash", "zsh")),
            # Options.
            ("-c", ("--login", "-c")),
        )
    ) + [None]


def _python_invocation_matrix():
    """Pre-compute a matrix of all possible options used for python invocation.

    Returns
    -------
    ```{code-block} python
    (
        ("python",),
        ("python3",),
        ("/usr/bin/env", "python"),
        ("/usr/bin/env", "python3"),
    )
    ```
    """
    return _invocation_matrix(
        # Env prefixes.
        (None, "/usr/bin/env"),
        # Binary paths
        ("python", "python3"),
    )


shell_args = pytest.mark.parametrize(
    "shell_args",
    tuple(
        pytest.param(p, id=" ".join(args_cleanup(p)))
        for p in _shell_invocation_matrix()
    ),
)


shell_python_args = pytest.mark.parametrize(
    "shell_args,python_args",
    tuple(
        pytest.param(s_args, p_args, id=" ".join(args_cleanup(s_args, p_args)))
        for s_args, p_args in product(
            _shell_invocation_matrix(), _python_invocation_matrix()
        )
    ),
)


def _subcmd_args(
    invoke_args: tuple[str, ...] | None, *subcmd_args: str
) -> tuple[str, ...]:
    """Cleanup args and eventually concatenate all `subcmd_args` items to a space
    separated string if `invoke_args` is defined and its last argument is equal to
    `-c`."""
    raw_args: list[str] = []
    if invoke_args:
        raw_args.extend(invoke_args)
        if invoke_args[-1] == "-c":
            subcmd_args = (" ".join(subcmd_args),)
    raw_args.extend(subcmd_args)
    return args_cleanup(raw_args)


# The plugin suite drives mpm end-to-end and needs at least one live package
# manager on the host, so it belongs to the integration layer even though its
# module name does not match the `test_cli*` / `test_manager_*` convention
# conftest keys on. The marker makes `-m "not integration"` and the hermetic-
# build auto-skip cover it too.
@pytest.mark.integration
@unless_macos
class TestBarPlugin:
    common_checklist: ClassVar[list] = [
        # Menubar line. Required.
        (r"(🎁↑\d+|📦✓)( ⚠️\d+)? \| dropdown=false$", True),
        # Submenus and sections marker. Required.
        (r"-{3,5}$", True),
        # Upgrade all line.
        # XXX Upgrade all line is not required, as it may be skipped in the
        # final rendering of the plugin if no outdated packages are found:
        #     📦✓ ⚠️1 | dropdown=false
        #     ---
        #     brew - 0 package | font=Menlo size=12
        #     ---
        #     cask - 0 package | font=Menlo size=12
        #     ...
        (
            (
                r"(--)?🆙 Upgrade all \S+ packages? \| shell=\S+( param\d+=\S+)+ "
                r"refresh=true terminal=(true|false alternate=true)$"
            ),
            False,
        ),
        # Error line. Optional.
        (
            (
                r"(--)?.+ \| font=[Mm]enlo size=12 color=red trim=false "
                r"ansi=false emojize=false( symbolize=false)?$"
            ),
            False,
        ),
        # About footer. Every one of its rows is required: the footer closes
        # any menu that renders at all, and these runs all render one.
        (r"About \|( .+)?$", True),
        (r"--Meta Package Manager \((SwiftBar|Xbar) plugin\) \S+ \|( .+)?$", True),
        (r"--mpm (\S+|not found) \|( .+)?$", True),
        # The resolved mpm command, the one About row carrying a path.
        (r"--[^|]+ \| font=[Mm]enlo size=12$", True),
        (r"--Documentation \| href=\S+( .+)?$", True),
    ]

    def _plugin_output_checks(self, checklist, extra_env: TEnvVars | None = None):
        """Run the plugin script and check its output against the checklist.

        The ambient color knobs (`NO_COLOR`, `LLM`, `TERM=dumb`, ...) are
        scrubbed from the subprocess environment so the run reflects a real
        bar app launch: exported by the developer shell or the CI runner,
        they would otherwise disable the version-diff colors mpm forces for
        plugin output.
        """
        env = {**os.environ, **(extra_env or {})}
        for var in (*COLOR_ENVVARS, "TERM"):
            env.pop(var, None)
        process = subprocess.run(
            bar_plugin.__file__,
            capture_output=True,
            encoding="utf-8",
            env=cast("subprocess._ENV", env),
            check=False,
        )

        assert not process.stderr
        assert process.returncode == 0

        checks = checklist + self.common_checklist

        match_counter = Counter()  # type: ignore[var-annotated]

        for line in process.stdout.splitlines():
            # The line is expected to match at least one regex.
            matches = False
            for index, (regex, _) in enumerate(checks):
                if re.match(regex, line):
                    matches = True
                    match_counter[index] += 1
                    break
            if not matches:
                print(process.stdout)
                msg = f"plugin output line {line!r} did not match any regex."
                raise Exception(msg)  # noqa: TRY002

        # Check all required regex did match at least once.
        for index, (regex, required) in enumerate(checks):
            if required and not match_counter[index]:
                print(process.stdout)
                msg = f"{regex!r} regex did not match any plugin output line."
                raise Exception(msg)  # noqa: TRY002

        # A package line declaring ansi=true must back it with actual escape
        # codes: the version-diff colors survive the non-TTY pipe the plugin
        # captures mpm's output through. Opportunistic, as the host may have
        # no outdated package to render.
        for line in process.stdout.splitlines():
            if "ansi=true" in line and "→" in line:
                assert "\x1b[" in line

    @pytest.mark.xdist_group(name="avoid_concurrent_plugin_runs")
    @pytest.mark.parametrize("group_by_manager", (True, False, None))
    @pytest.mark.parametrize("align_columns", (True, False, None))
    def test_rendering(self, group_by_manager, align_columns):
        extra_checks: list[tuple[str, bool]] = []
        # XXX Package upgrade line is not required, as it may be skipped in the
        # final rendering of the plugin if no outdated packages are found:
        #     📦✓ ⚠️1 | dropdown=false
        #     ---
        #     brew - 0 package | font=Menlo size=12
        #     ---
        #     cask - 0 package | font=Menlo size=12
        #     ...
        if align_columns is False:
            extra_checks.extend(
                (
                    # Package manager section header.
                    (r"(⚠️ )?\d+ outdated .+ packages?", True),
                    # Package upgrade line.
                    (
                        (
                            r"(--)?[\S ]+ \S+ → \S+ \| shell=\S+( param\d+=\S+)+ "
                            r"ansi=true refresh=true "
                            r"terminal=(true|false alternate=true)$"
                        ),
                        False,
                    ),
                ),
            )
        # Default case is VAR_ALIGN_COLUMNS=true.
        else:
            extra_checks.extend(
                (
                    # Package manager section header.
                    (r"(⚠️ )?\S+ - \d+ packages?\s+\| font=[Mm]enlo size=12", True),
                    # Package upgrade line.
                    (
                        (
                            r"(--)?[\S ]+\s+\S+ → \S+\s+\| shell=\S+( param\d+=\S+)+ "
                            r"font=[Mm]enlo size=12 ansi=true refresh=true "
                            r"terminal=(true|false alternate=true)?$"
                        ),
                        False,
                    ),
                ),
            )

        extra_env = {}
        if group_by_manager is not None:
            extra_env["VAR_GROUP_BY_MANAGER"] = str(group_by_manager)
        if align_columns is not None:
            extra_env["VAR_ALIGN_COLUMNS"] = str(align_columns)

        self._plugin_output_checks(extra_checks, extra_env=extra_env)

    @pytest.mark.xdist_group(name="avoid_concurrent_plugin_runs")
    @shell_args
    def test_plugin_shell_invocation(self, shell_args):
        """Test execution of plugin on different shells.

        Do not execute the complete search for outdated packages, just stop at searching
        for the mpm executable and extract its version.
        """
        process = subprocess.run(
            _subcmd_args(shell_args, bar_plugin.__file__, "--search-mpm"),
            capture_output=True,
            encoding="utf-8",
            check=False,
        )

        assert not process.stderr
        assert process.returncode == 0
        assert process.stdout
        for line in process.stdout.splitlines():
            assert re.match(
                r"^.+ \| runnable: \S+ \| up to date: \S+"
                r" \| version: .+ \| error: .*$",
                line,
            )

    @shell_python_args
    def test_python_shell_invocation(self, shell_args, python_args):
        """Test any Python shell invocation is properly configured and all are
        compatible with plugin requirements."""
        process = subprocess.run(
            _subcmd_args(shell_args, *python_args, "--version"),
            capture_output=True,
            encoding="utf-8",
            check=False,
        )

        assert not process.stderr
        assert process.stdout
        assert process.returncode == 0

        # We need to parse the version to account for alpha release,
        # like Python `3.12.0a4`.
        # The bar plugin itself must run on macOS system Python (3.9+), even though
        # mpm requires 3.10+. The check_mpm() runnability test catches the gap.
        python_version = process.stdout.split()[1]
        assert parse_version(python_version) >= parse_version(
            "3.9",
        ), f"{python_version} >= 3.9"
