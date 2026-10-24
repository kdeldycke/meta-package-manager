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

"""bin output tests.

These tests stand in for the child process, so the report reaches
{meth}`~meta_package_manager.execution.CLIExecutor.run` and its failure gate the
way a real one does. They never call `bin`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from meta_package_manager.managers.bin import DRY_RUN_UPDATES_FOUND, Bin

DRY_RUN_REPORT = """\
  • /home/user/.local/bin/fzf v0.40.0 -> v0.74.2 (https://github.com/junegunn/fzf/releases/tag/v0.74.2)
  • /home/user/.local/bin/gh v2.40.0 -> v2.97.0 (https://github.com/cli/cli/releases/tag/v2.97.0)
  ⨯ command failed                                   error=Updates found, exit (dry-run mode).
"""
"""The `<stderr>` of `bin update --dry-run`, as the docstring of
{attr}`~meta_package_manager.managers.bin.Bin.outdated` shows it."""


@pytest.fixture
def manager(monkeypatch):
    """A `bin` manager whose binary is never looked up."""
    bin_manager = Bin()
    monkeypatch.setattr(
        bin_manager, "cli_path", Path("/usr/local/bin/bin"), raising=False
    )
    return bin_manager


@pytest.mark.parametrize(
    ("code", "stderr", "expected", "kept_errors"),
    (
        pytest.param(
            DRY_RUN_UPDATES_FOUND,
            DRY_RUN_REPORT,
            [
                ("/home/user/.local/bin/fzf", "v0.40.0", "v0.74.2"),
                ("/home/user/.local/bin/gh", "v2.40.0", "v2.97.0"),
            ],
            0,
            id="updates-found",
        ),
        pytest.param(0, "", [], 0, id="up-to-date"),
        # The same report under an exit code that is neither of the two: the
        # check failed, so nothing is read and the failure is kept.
        pytest.param(1, DRY_RUN_REPORT, [], 1, id="check-failed"),
    ),
)
def test_outdated_reads_the_dry_run_report(
    manager, monkeypatch, code, stderr, expected, kept_errors
):
    """The exit code decides whether the report is a result or a failure."""
    monkeypatch.setattr(manager, "_spawn", lambda *args, **kwargs: (code, "", stderr))
    packages = [
        (p.id, str(p.installed_version), str(p.latest_version))
        for p in manager.outdated
    ]
    assert packages == expected
    assert len(manager.cli_errors) == kept_errors


def test_outdated_without_a_completed_run(manager, monkeypatch):
    """A dry run that never completed leaves no report to read."""
    monkeypatch.setattr(manager, "_spawn", lambda *args, **kwargs: None)
    assert list(manager.outdated) == []
