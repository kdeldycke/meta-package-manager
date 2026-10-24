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

from .conftest import default_manager_ids, tomllib
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
        f":{mid}.installed: Dump installed packages." in stderr,
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


def test_output_to_console(invoke, subcmd, fake_pool):
    """An explicit `-` target prints to `<stdout>`.

    The three destination tests below run on the fake pool: what varies
    between them is where the snapshot lands, not what is in it, and
    re-collecting the host's inventory for each cost twenty seconds a case.
    `test_default_all_managers_output_to_console` keeps the live one.
    """
    result = invoke(subcmd, "-")
    assert result.exit_code == 0
    assert "Print installed package list to <stdout>" in result.stderr


def test_output_to_file(invoke, subcmd, fake_pool):
    result = invoke(subcmd, "mpm-packages.toml")
    assert result.exit_code == 0
    assert "mpm-packages.toml" in result.stderr


def test_output_to_file_creates_missing_parents(invoke, subcmd, fake_pool):
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


@pytest.mark.parametrize("flag", ("--merge", "--update-version"))
def test_in_place_modes_need_a_file(invoke, subcmd, fake_pool, flag):
    """`--merge` and `--update-version` edit a file, so `<stdout>` is refused."""
    result = invoke(subcmd, flag)
    assert result.exit_code == 2
    assert not result.stdout
    assert f"{flag} requires the [OUTPUT_PATH] argument to point to a file." in (
        result.stderr
    )


@pytest.mark.parametrize("flag", ("--merge", "--update-version"))
def test_in_place_modes_need_an_existing_file(invoke, subcmd, fake_pool, flag):
    """There is nothing to edit in place when the target does not exist yet."""
    result = invoke(subcmd, flag, "mpm-packages.toml")
    assert result.exit_code == 2
    assert f"{flag} requires an existing file." in result.stderr
    assert not Path("mpm-packages.toml").exists()


def test_merge_and_update_version_are_exclusive(invoke, subcmd, fake_pool):
    target = Path("mpm-packages.toml")
    target.write_text('[fakemanager]\nfake-pkg-gamma = "0.1.0"\n', encoding="UTF-8")
    result = invoke(subcmd, "--merge", "--update-version", str(target))
    assert result.exit_code == 2
    assert "--merge and --update-version are mutually exclusive." in result.stderr


def test_overwrite_is_ignored_on_stdout(invoke, subcmd, fake_pool):
    result = invoke(subcmd, "--overwrite")
    assert result.exit_code == 0
    assert "Ignore the --overwrite/--force/--replace option." in result.stderr
    assert "fake-pkg-alpha" in result.stdout


def test_target_must_be_a_toml_file(invoke, subcmd, fake_pool):
    result = invoke(subcmd, "mpm-packages.txt")
    assert result.exit_code == 2
    assert "Target file is not a TOML file." in result.stderr
    assert not Path("mpm-packages.txt").exists()


@pytest.mark.parametrize("flag", ("--overwrite", "--force", "--replace"))
def test_existing_target_needs_overwrite(invoke, subcmd, fake_pool, flag):
    """An existing snapshot survives a dump, unless one of the overwrite flags is
    passed."""
    target = Path("mpm-packages.toml")
    target.write_text('[fakemanager]\nfake-pkg-gamma = "0.1.0"\n', encoding="UTF-8")

    result = invoke(subcmd, str(target))
    assert result.exit_code == 2
    assert "critical: Target file exist and will be overwritten." in result.stderr
    assert "fake-pkg-gamma" in target.read_text(encoding="UTF-8")

    result = invoke(subcmd, flag, str(target))
    assert result.exit_code == 0
    assert "warning: Target file exist and will be overwritten." in result.stderr
    assert tomllib.loads(target.read_text(encoding="UTF-8")) == {
        "fakemanager": {"fake-pkg-alpha": "1.0.0", "fake-pkg-beta": "2.5.3"},
    }


@pytest.mark.parametrize("overwrite", (True, False))
def test_merge_adds_new_entries(invoke, subcmd, fake_pool, overwrite):
    """A merge writes each installed package at its installed version, and keeps
    the entries of the packages that are not installed. It removes nothing, so an
    overwrite flag is inert."""
    target = Path("mpm-packages.toml")
    target.write_text(
        '[fakemanager]\nfake-pkg-alpha = "0.9.0"\nfake-pkg-gamma = "0.1.0"\n',
        encoding="UTF-8",
    )
    args = ("--overwrite",) if overwrite else ()

    result = invoke(subcmd, "--merge", *args, str(target))
    assert result.exit_code == 0
    assert f"Merge all installed packages into {target.resolve()}" in result.stderr
    assert ("Ignore the --overwrite/--force/--replace option." in result.stderr) is (
        overwrite
    )
    assert tomllib.loads(target.read_text(encoding="UTF-8")) == {
        "fakemanager": {
            "fake-pkg-alpha": "1.0.0",
            "fake-pkg-beta": "2.5.3",
            "fake-pkg-gamma": "0.1.0",
        },
    }
    assert "3 packages total (fakemanager: 3)." in result.stderr


def test_update_version_refreshes_listed_entries(invoke, subcmd, fake_pool):
    """An update refreshes the version of each listed package that is installed,
    and adds nothing: `fake-pkg-beta` is installed but not listed."""
    target = Path("mpm-packages.toml")
    target.write_text(
        '[fakemanager]\nfake-pkg-alpha = "0.9.0"\nfake-pkg-gamma = "0.1.0"\n',
        encoding="UTF-8",
    )

    result = invoke(subcmd, "--update-version", str(target))
    assert result.exit_code == 0
    assert "Update in-place all versions of installed packages found in" in (
        result.stderr
    )
    assert tomllib.loads(target.read_text(encoding="UTF-8")) == {
        "fakemanager": {"fake-pkg-alpha": "1.0.0", "fake-pkg-gamma": "0.1.0"},
    }
