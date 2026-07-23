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
"""Pip-specific tests for bundled-app detection and interpreter discovery."""

from __future__ import annotations

import importlib.metadata
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from meta_package_manager.execution import CLIExecutor
from meta_package_manager.managers.pip import Pip

PATCH_DIST = "meta_package_manager.managers.pip.importlib.metadata.distribution"
PATCH_PREFIX = "meta_package_manager.managers.pip.sys.prefix"
PATCH_EXEC = "meta_package_manager.managers.pip.sys.executable"
PATCH_RUN = "meta_package_manager.managers.pip.subprocess.run"


def _installer_dist(installer):
    """Mock distribution exposing the given `INSTALLER` dist-info record."""
    dist = MagicMock()
    dist.read_text = lambda name: f"{installer}\n" if name == "INSTALLER" else None
    return dist


# --- Guard one: mpm's own distributor-managed bundle. ------------------------


def test_bundled_app_detected_under_cellar():
    """A `sys.prefix` under a Homebrew Cellar is conclusive on its own."""
    cellar = "/opt/homebrew/Cellar/meta-package-manager/7.0.0/libexec"
    with (
        patch(PATCH_PREFIX, cellar),
        # The INSTALLER lookup must not even be consulted when Cellar matches.
        patch(PATCH_DIST, side_effect=AssertionError("must not be called")),
    ):
        assert Pip._running_from_bundled_app() is True


@pytest.mark.parametrize(
    "prefix",
    ["/usr", "/home/kde/.venv", "/opt/homebrew", "/opt/homebrew/opt/python@3.14"],
)
def test_bundled_app_detected_by_brew_installer(prefix):
    """Outside Cellar, an `INSTALLER` of `brew` still flags the bundle."""
    with (
        patch(PATCH_PREFIX, prefix),
        patch(PATCH_DIST, return_value=_installer_dist("brew")),
    ):
        assert Pip._running_from_bundled_app() is True


def test_brew_installer_case_and_whitespace_insensitive():
    """The `INSTALLER` tag is matched case- and whitespace-insensitively."""
    with (
        patch(PATCH_PREFIX, "/usr"),
        patch(PATCH_DIST, return_value=_installer_dist("  Brew  ")),
    ):
        assert Pip._running_from_bundled_app() is True


@pytest.mark.parametrize("installer", ["pip", "uv", "poetry", ""])
def test_user_install_not_flagged(installer):
    """A user-managed install (pip/uv/...) outside Cellar is not a bundle."""
    with (
        patch(PATCH_PREFIX, "/home/kde/project/.venv"),
        patch(PATCH_DIST, return_value=_installer_dist(installer)),
    ):
        assert Pip._running_from_bundled_app() is False


def test_bundled_app_false_when_mpm_absent():
    """Running from source (`mpm` not installed) is not a bundle."""
    with (
        patch(PATCH_PREFIX, "/home/kde/project/.venv"),
        patch(PATCH_DIST, side_effect=importlib.metadata.PackageNotFoundError("x")),
    ):
        assert Pip._running_from_bundled_app() is False


# --- Guard two: PEP 668 externally-managed, non-virtualenv interpreters. ------


def _completed(stdout):
    """Mock a `subprocess.run` result carrying the given stdout."""
    result = MagicMock()
    result.stdout = stdout
    return result


@pytest.mark.parametrize(
    ("stdout", "expected"),
    [("1\n", True), ("1", True), ("0\n", False), ("", False), ("oops", False)],
)
def test_pip_install_blocked_parses_probe(stdout, expected):
    """The probe's `1`/`0` output maps to blocked/not-blocked."""
    candidate = Path("/usr/bin/python3")
    with patch(PATCH_RUN, return_value=_completed(stdout)) as run:
        assert Pip()._pip_install_blocked(candidate) is expected
    # The candidate interpreter runs the externally-managed one-liner. Compare
    # against the same str() conversion the probe applies, so the expectation
    # holds on Windows where the path stringifies with backslashes.
    command = run.call_args.args[0]
    assert command[0] == str(candidate)
    assert command[1] == "-c"
    assert "EXTERNALLY-MANAGED" in command[2]


@pytest.mark.parametrize(
    "error",
    [OSError("not a python"), subprocess.TimeoutExpired("python", 1)],
)
def test_pip_install_blocked_keeps_candidate_on_error(error):
    """A failed probe must not hide a candidate: default to not-blocked."""
    with patch(PATCH_RUN, side_effect=error):
        assert Pip()._pip_install_blocked(Path("/usr/bin/python3")) is False


# --- Discovery: both guards composed in search_all_cli. -----------------------


def _fake_base_search(self, cli_names, env=None):
    """Stand-in for the base `PATH` search yielding two fixed interpreters."""
    yield Path("/usr/bin/python3")
    yield Path("/usr/local/bin/python3")


def test_search_prepends_current_interpreter_for_user_install():
    """A normal install probes the running interpreter first."""
    fake_exec = "/home/kde/project/.venv/bin/python"
    with (
        patch(PATCH_EXEC, fake_exec),
        patch.object(Pip, "_running_from_bundled_app", return_value=False),
        patch.object(Pip, "_pip_install_blocked", return_value=False),
        patch.object(CLIExecutor, "search_all_cli", _fake_base_search),
    ):
        found = list(Pip().search_all_cli(("python3", "python")))
    assert found == [
        Path(fake_exec),
        Path("/usr/bin/python3"),
        Path("/usr/local/bin/python3"),
    ]


def test_search_skips_bundled_interpreter():
    """A distributor bundle skips the running interpreter and falls back to PATH."""
    fake_exec = "/opt/homebrew/Cellar/meta-package-manager/7.0.0/libexec/bin/python"
    with (
        patch(PATCH_EXEC, fake_exec),
        patch.object(Pip, "_running_from_bundled_app", return_value=True),
        patch.object(Pip, "_pip_install_blocked", return_value=False),
        patch.object(CLIExecutor, "search_all_cli", _fake_base_search),
    ):
        found = list(Pip().search_all_cli(("python3", "python")))
    assert Path(fake_exec) not in found
    assert found == [Path("/usr/bin/python3"), Path("/usr/local/bin/python3")]


def test_search_skips_pep668_blocked_candidate():
    """Externally-managed, non-virtualenv interpreters (PEP 668) are dropped."""
    fake_exec = "/home/kde/project/.venv/bin/python"
    blocked = Path("/usr/bin/python3")
    with (
        patch(PATCH_EXEC, fake_exec),
        patch.object(Pip, "_running_from_bundled_app", return_value=False),
        patch.object(
            Pip, "_pip_install_blocked", side_effect=lambda path: path == blocked
        ),
        patch.object(CLIExecutor, "search_all_cli", _fake_base_search),
    ):
        found = list(Pip().search_all_cli(("python3", "python")))
    assert blocked not in found
    assert found == [Path(fake_exec), Path("/usr/local/bin/python3")]


def test_search_unavailable_when_all_candidates_blocked():
    """With every interpreter blocked, discovery yields nothing (pip unavailable)."""
    fake_exec = "/opt/homebrew/bin/python3"
    with (
        patch(PATCH_EXEC, fake_exec),
        patch.object(Pip, "_running_from_bundled_app", return_value=False),
        patch.object(Pip, "_pip_install_blocked", return_value=True),
        patch.object(CLIExecutor, "search_all_cli", _fake_base_search),
    ):
        found = list(Pip().search_all_cli(("python3", "python")))
    assert found == []
