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
from operator import attrgetter
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from click_extra.platforms import is_macos

# Pre-load invocation helpers to be used as pytest's fixture.
from click_extra.tests.conftest import extra_runner  # noqa: F401
from pytest import fixture, param

from meta_package_manager.cli import mpm
from meta_package_manager.pool import manager_classes, pool

if TYPE_CHECKING:
    from _pytest.config import Config

""" Fixtures, configuration and helpers for tests. """


def pytest_addoption(parser):
    """Add custom command line options.

    Based on `Pytest's documentation examples
    <https://docs.pytest.org/en/latest/example/simple.html#control-skipping-of-tests-according-to-command-line-option>`_.

    By default, runs non-destructive tests and skips destructive ones.
    """
    parser.addoption(
        "--run-destructive",
        action="store_true",
        default=False,
        help="Run the subset of tests that are marked as destructive.",
    )
    parser.addoption(
        "--skip-destructive",
        action="store_true",
        default=False,
        help="Skip the subset of tests that are marked as destructive. "
        "Takes precedence over --run-destructive.",
    )

    parser.addoption(
        "--run-non-destructive",
        action="store_true",
        default=True,
        help="Run the subset of tests that are marked as non-destructive.",
    )
    parser.addoption(
        "--skip-non-destructive",
        action="store_true",
        default=False,
        help="Skip the subset of tests that are marked as non-destructive. "
        "Takes precedence over --run-non-destructive.",
    )


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "destructive: mark test as being destructive, "
        "i.e. modifying the system they run on.",
    )


def solve_destructive_options(config: Config) -> tuple[bool, bool]:
    """Solve the destructive options to determine which tests to run."""
    run_destructive = config.getoption("--run-destructive")
    run_non_destructive = config.getoption("--run-non-destructive")

    # Skip options take precedence over run options.
    if config.getoption("--skip-destructive"):
        run_destructive = False
    if config.getoption("--skip-non-destructive"):
        run_non_destructive = False

    if not run_destructive and not run_non_destructive:
        msg = (
            "Both destructive and non-destructive tests were skipped. No tests to run."
        )
        raise ValueError(msg)

    return run_destructive, run_non_destructive


def pytest_collection_modifyitems(config, items):
    """Either skip or run destructive tests based on command line options."""
    run_destructive, run_non_destructive = solve_destructive_options(config)

    # Skip destructive tests.
    if not run_destructive:
        skip_destructive = pytest.mark.skip(reason="skip destructive tests")
        for item in items:
            if "destructive" in item.keywords:
                item.add_marker(skip_destructive)

    # Skip non-destructive tests.
    if not run_non_destructive:
        skip_non_destructive = pytest.mark.skip(reason="skip non-destructive tests")
        for item in items:
            if "destructive" not in item.keywords:
                item.add_marker(skip_non_destructive)


def pytest_report_header(config: Config, start_path: Path) -> tuple[str, ...]:
    """Display destructive options status in test report header."""
    run_destructive = config.getoption("--run-destructive")
    skip_destructive = config.getoption("--skip-destructive")
    run_non_destructive = config.getoption("--run-non-destructive")
    skip_non_destructive = config.getoption("--skip-non-destructive")
    run_destructive_tests, run_non_destructive_tests = solve_destructive_options(config)
    return (
        f"--run-destructive={run_destructive}",
        f"--skip-destructive={skip_destructive}",
        f"--run-non-destructive={run_non_destructive}",
        f"--skip-non-destructive={skip_non_destructive}",
        f"Run destructive tests: {run_destructive_tests}",
        f"Run non-destructive tests: {run_non_destructive_tests}",
    )


@fixture
def invoke(extra_runner):  # noqa: F811
    return partial(extra_runner.invoke, mpm)


@fixture(scope="class")
def subcmd():
    """Fixture used in ``test_cli_*.py`` files to set the subcommand arguments in all
    CLI calls.

    Must returns a string or an iterable of strings. Defaults to ``None``, which allows
    tests relying on this fixture to selectively skip running.
    """
    return


PACKAGE_IDS = {
    "apm": "markdown-pdf",
    "apt": "wget",
    "apt-mint": "exiftool",
    # https://github.com/Homebrew/homebrew-core/blob/master/Formula/meta-package-manager.rb
    "brew": "meta-package-manager",
    "cargo": "colorous",
    "cask": "pngyu",
    "choco": "ccleaner",
    "composer": "illuminate/contracts",
    "dnf": "usd",
    "emerge": "dev-vcs/git",
    "flatpak": "org.gnome.Dictionary",
    "gem": "markdown",
    "mas": "747648890",  # Telegram
    "npm": "raven",
    "opkg": "enigma2-hotplug",
    "pacaur": "manjaro-hello",
    "pacman": "manjaro-hello",
    # https://aur.archlinux.org/packages/meta-package-manager
    "paru": "meta-package-manager",
    # https://pypi.org/project/meta-package-manager
    "pip": "meta-package-manager",
    # https://pypi.org/project/meta-package-manager
    "pipx": "meta-package-manager",
    "pkg": "dmg2img",
    "scoop": "7zip",
    "snap": "standard-notes",
    "steamcmd": "740",
    "vscode": "tamasfe.even-better-toml",
    "yarn": "awesome-lint",
    # https://aur.archlinux.org/packages/meta-package-manager
    "yay": "meta-package-manager",
    "yum": "usd",
    "zypper": "git",
}
"""List of existing package IDs to install for each supported package manager.

Only to be used for destructive tests.
"""

assert set(PACKAGE_IDS) == set(pool.all_manager_ids)

# Collection of pre-computed parametrized decorators.

all_managers = pytest.mark.parametrize("manager", pool.values(), ids=attrgetter("id"))
available_managers = pytest.mark.parametrize(
    "manager",
    tuple(m for m in pool.values() if m.available),
    ids=attrgetter("id"),
)

all_manager_ids = pytest.mark.parametrize("manager_id", pool.all_manager_ids)
maintained_manager_ids = pytest.mark.parametrize(
    "manager_id",
    pool.maintained_manager_ids,
)
default_manager_ids = pytest.mark.parametrize("manager_id", pool.default_manager_ids)
unsupported_manager_ids = pytest.mark.parametrize(
    "manager_id",
    pool.unsupported_manager_ids,
)

manager_classes = pytest.mark.parametrize(  # type: ignore[assignment]
    "manager_class",
    manager_classes,
    ids=attrgetter("name"),
)

all_manager_ids_and_dummy_package = pytest.mark.parametrize(
    "manager_id,package_id",
    (param(*v, id=v[0]) for v in PACKAGE_IDS.items()),
)
available_managers_and_dummy_package = pytest.mark.parametrize(
    "manager,package_id",
    (param(m, PACKAGE_IDS[mid], id=mid) for mid, m in pool.items() if m.available),
)


# XXX Deactivate hack while we investigate.
# @pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item, nextitem):
    """Force the reset, after each subcommand test, of NPM's cached CLI path.

    This hack is applied on macOS only, in which parallel tests are messing up with the
    location of the system's NPM binary. This ends up in cryptic test suite failures,
    as the ``npm`` CLI is moved around during execution:

    .. code-block:: pytb
        Traceback (most recent call last):
          File ".../site-packages/click/testing.py", line 408, in invoke
            return_value = cli.main(args=args or (), prog_name=prog_name, **extra)
          File ".../site-packages/click_extra/commands.py", line 161, in main
            return super().main(*args, **kwargs)
          File ".../site-packages/click/core.py", line 1055, in main
            rv = self.invoke(ctx)
          File ".../site-packages/click_extra/commands.py", line 214, in invoke
            return super().invoke(ctx)
          File ".../site-packages/click/core.py", line 1657, in invoke
            return _process_result(sub_ctx.command.invoke(sub_ctx))
          File ".../site-packages/click/core.py", line 1404, in invoke
            return ctx.invoke(self.callback, **ctx.params)
          File ".../site-packages/click/core.py", line 760, in invoke
            return __callback(*args, **kwargs)
          File ".../site-packages/click/decorators.py", line 26, in new_func
            return f(get_current_context(), *args, **kwargs)
          File ".../meta_package_manager/cli.py", line 864, in upgrade
            output = manager.upgrade()
          File ".../meta_package_manager/base.py", line 863, in upgrade
            return self.run(cli, extra_env=self.extra_env)
          File ".../meta_package_manager/base.py", line 551, in run
            code, output, error = run_cmd(
          File ".../site-packages/click_extra/run.py", line 111, in run_cmd
            process = subprocess.run(
          File ".../python3.8/subprocess.py", line 493, in run
            with Popen(*popenargs, **kwargs) as process:
          File ".../python3.8/subprocess.py", line 858, in __init__
            self._execute_child(args, executable, preexec_fn, close_fds,
          File ".../python3.8/subprocess.py", line 1704, in _execute_child
            raise child_exception_type(errno_num, err_msg, err_filename)
        FileNotFoundError: [Errno 2] No such file or directory: '/usr/local/bin/npm'

    Clearing the ``cli_path`` cached property forces ``mpm`` to re-search the ``npm``
    binary on the system.
    """
    # Let pytest finish the test as-is.
    outcome = yield  # noqa: F841

    # Only inspect tests that are part of a suit wrapped in a class, and only on macOS.
    if item.parent.cls and is_macos():
        # Work around circular imports.
        from .test_cli import CLISubCommandTests

        # Only apply this hack to subcommand tests.
        if CLISubCommandTests in item.parent.cls.mro():
            npm = pool.get("npm")
            # Inspect the internal dict to avoid calling the property or ``getattr``,
            # as both will trigger the caching mechanism.
            if "cli_path" in npm.__dict__:
                # Reset cached cli_path to force re-detection of the CLI.
                del npm.cli_path

            # Force recompute of the CLI path.
            cli_path = npm.cli_path
            if cli_path:
                assert isinstance(npm.cli_path, Path)
