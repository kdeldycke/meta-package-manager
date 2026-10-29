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
"""`mpm dump` CLI tests.

Drives the subcommand against the deterministic `fake_pool`. The Brewfile
renderer it delegates to is unit-tested in {mod}`tests.test_brewfile`, and the
snapshot/merge/update flows shared with the `backup` alias live in
{mod}`tests.test_cli_backup`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from .fake_manager import FakeManager


class BrewFakeManager(FakeManager):
    """A fake whose packages map to `brew` lines of a Brewfile."""

    brewfile_entry_type = "brew"


class WarnedFakeManager(FakeManager):
    """A fake with no Brewfile mapping, which warns about the packages it drops."""

    brewfile_skip_warning = "Skipping {count} packages with no Brewfile entry type."


class BrokenFakeManager(FakeManager):
    """A fake with no Brewfile mapping, whose inventory command fails.

    The failure goes through
    {meth}`~meta_package_manager.execution.CLIExecutor.run`, which records it
    in {attr}`~meta_package_manager.execution.CLIExecutor.cli_errors` the way a
    real manager does.
    """

    @property
    def installed(self):
        self.run(str(self.cli_path), "-c", "import sys; sys.exit('No database.')")
        return iter(())


BREW_LINES = 'brew "fake-pkg-alpha"\nbrew "fake-pkg-beta"\n'
"""The Brewfile entries of the two packages {class}`BrewFakeManager` lists."""


@pytest.fixture
def brewfile_pool(patch_pool_with):
    """Select a mapped manager, a warned one and a broken one, in that order."""
    return patch_pool_with(BrewFakeManager(), WarnedFakeManager(), BrokenFakeManager())


@pytest.mark.parametrize(
    ("args", "listed"),
    (
        # A query keeps only the installed packages matching it.
        pytest.param(("--query", "alpha"), {"fake-pkg-alpha"}, id="query"),
        # Without a query, the whole installed inventory is kept.
        pytest.param((), {"fake-pkg-alpha", "fake-pkg-beta"}, id="no-query"),
    ),
)
def test_dump_query_filter(invoke, fake_pool, args, listed):
    result = invoke("dump", *args)
    assert result.exit_code == 0
    for package_id in ("fake-pkg-alpha", "fake-pkg-beta"):
        assert (package_id in result.stdout) is (package_id in listed)


@pytest.mark.parametrize("flag", ("--merge", "--update-version"))
def test_dump_brewfile_rejects_toml_only_flags(invoke, fake_pool, flag):
    """`--merge` and `--update-version` edit a TOML manifest, never a Brewfile."""
    result = invoke("dump", "--brewfile", flag, "Brewfile")
    assert result.exit_code == 2
    assert not result.stdout
    assert "--merge / --update-version cannot be combined with --brewfile." in (
        result.stderr
    )
    assert not Path("Brewfile").exists()


def test_dump_brewfile_to_stdout(invoke, brewfile_pool):
    """Only the mapped manager reaches the Brewfile, and the summary counts its
    entries by type.
    """
    result = invoke(
        "--verbosity", "INFO", "dump", "--brewfile", "--no-header", "--overwrite"
    )
    assert result.exit_code == 0
    assert result.stdout == BREW_LINES
    assert "Ignore the --overwrite/--force/--replace option." in result.stderr
    assert "Print Brewfile to <stdout>" in result.stderr
    assert "2 packages total (brew: 2)." in result.stderr


def test_dump_brewfile_header_tallies_skipped_managers(invoke, brewfile_pool):
    """The header counts the packages of an unmapped manager, which also gets its
    warning, and leaves out the manager whose inventory failed.
    """
    result = invoke("dump", "--brewfile")
    assert result.exit_code == 0
    assert result.stdout.endswith(f"\n\n{BREW_LINES}")
    assert "# Coverage: brewfakemanager=2\n" in result.stdout
    assert "# Skipped:  warnedfakemanager=2\n" in result.stdout
    assert "brokenfakemanager" not in result.stdout
    assert "Skipping 2 packages with no Brewfile entry type." in result.stderr


def test_dump_brewfile_to_file_guards_an_existing_target(invoke, brewfile_pool):
    """A Brewfile already on disk survives a dump, unless `--overwrite` is passed."""
    target = Path("Brewfile")
    target.write_bytes(b'brew "wget"\n')

    result = invoke("dump", "--brewfile", "--no-header", str(target))
    assert result.exit_code == 2
    assert "critical: Target file exist and will be overwritten." in result.stderr
    assert target.read_bytes() == b'brew "wget"\n'

    result = invoke("dump", "--brewfile", "--no-header", "--overwrite", str(target))
    assert result.exit_code == 0
    assert "warning: Target file exist and will be overwritten." in result.stderr
    assert target.read_text(encoding="UTF-8") == BREW_LINES
