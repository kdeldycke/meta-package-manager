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

from functools import partial
from pathlib import Path

import pytest

from meta_package_manager.capabilities import Operations

from .conftest import default_manager_ids
from .test_cli import assert_no_manager_selected, check_manager_selection


@pytest.fixture
def subcmd():
    # `DEBUG` level is required so that `check_manager_selection` can detect
    # skip/does-not-implement signals for implicitly selected managers. Those
    # messages are demoted to DEBUG when no explicit `--<id>` flag is passed.
    # INFO messages are a subset of DEBUG, so everything logged at INFO still
    # appears.
    return "--verbosity", "DEBUG", "backup"


def evaluate_signals(mid, stdout, stderr):
    yield from (
        f":{mid}: Dumping packages..." in stderr,
        # The glued `:<mid>:` label form matches whatever level the
        # message lands at: demoted to DEBUG for implicit selection
        # (`mpm backup`), INFO for explicit ones (`mpm --<mid> backup`).
        f":{mid}: Does not implement {Operations.installed}" in stderr,
        f":{mid}: Skipped:" in stderr,
    )


check_selection = partial(check_manager_selection, signals=evaluate_signals)
"""Selection assertions reading this subcommand's own signals."""


def test_default_all_managers_output_to_console(invoke, subcmd):
    result = invoke(subcmd)
    assert result.exit_code == 0
    assert "Print installed package list to <stdout>" in result.stderr
    check_selection(result)


def test_output_to_console(invoke, subcmd):
    result = invoke(subcmd, "-")
    assert result.exit_code == 0
    assert "Print installed package list to <stdout>" in result.stderr
    check_selection(result)


def test_output_to_file(invoke, subcmd):
    result = invoke(subcmd, "mpm-packages.toml")
    assert result.exit_code == 0
    assert "mpm-packages.toml" in result.stderr
    check_selection(result)


def test_output_to_file_creates_missing_parents(invoke, subcmd):
    """A destination whose directory does not exist yet is created, not an error.

    Regression: mpm used to open the target directly, so a path into a
    missing directory died on an unhandled `FileNotFoundError`. Adopting
    click-extra's `prep_path` brought the `mkdir -p` with it.
    """
    target = Path("snapshots") / "2026" / "mpm-packages.toml"
    result = invoke(subcmd, str(target))
    assert result.exit_code == 0
    assert target.is_file()


@default_manager_ids
def test_single_manager_file_output(manager_id, invoke, subcmd):
    result = invoke(
        "--verbosity", "INFO", f"--{manager_id}", subcmd, "mpm-packages.toml"
    )
    assert "mpm-packages.toml" in result.stderr
    if result.exit_code == 2:
        assert_no_manager_selected(result)
    else:
        assert result.exit_code == 0
        check_selection(result, {manager_id})
