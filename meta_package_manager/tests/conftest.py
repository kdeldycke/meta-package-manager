# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
# All Rights Reserved.
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

# pylint: disable=redefined-outer-name

import os
from pathlib import Path
from textwrap import dedent, indent

import click
import pytest
from boltons.iterutils import flatten, same
from boltons.strutils import strip_ansi
from boltons.tbutils import ExceptionInfo
from click.testing import CliRunner

from .. import CLI_NAME, config, reset_logger
from ..cli import cli
from ..platform import is_linux, is_macos, is_windows
from ..xbar import run as xbar_run

""" Fixtures, configuration and helpers for tests. """


MANAGER_IDS = frozenset(
    [
        "apm",
        "apt",
        "brew",
        "cask",
        "composer",
        "flatpak",
        "gem",
        "mas",
        "npm",
        "opkg",
        "pip",
        "snap",
        "vscode",
        "yarn",
    ]
)
""" Hard-coded list of all supported manager IDs. """


DESTRUCTIVE_MODE = bool(
    os.environ.get("DESTRUCTIVE_TESTS", False) not in {True, 1, "True", "true", "1"}
)
""" Pre-computed boolean flag indicating if destructive mode is activated by
the presence of a ``DESTRUCTIVE_TESTS`` environment variable set to ``True``.
"""


destructive = pytest.mark.skipif(DESTRUCTIVE_MODE, reason="destructive test")
""" Pytest mark to skip a test unless destructive mode is allowed.

.. todo:

    Test destructive test assessment.
"""


non_destructive = pytest.mark.skipif(
    not DESTRUCTIVE_MODE, reason="non-destructive test"
)
""" Pytest mark to skip a test unless destructive mode is allowed.

.. todo:

    Test destructive test assessment.
"""


unless_linux = pytest.mark.skipif(not is_linux(), reason="Linux required")
""" Pytest mark to skip a test unless it is run on a Linux system. """


unless_macos = pytest.mark.skipif(not is_macos(), reason="macOS required")
""" Pytest mark to skip a test unless it is run on a macOS system. """


unless_windows = pytest.mark.skipif(not is_windows(), reason="Windows required")
""" Pytest mark to skip a test unless it is run on a Windows system. """


def print_cli_output(cmd, output=None, error=None, error_code=None):
    """Simulate CLI output. Used to print debug traces in test results."""
    print("\n► {}".format(click.style(" ".join(cmd), fg="white")))
    margin = " " * 2
    if output:
        print(indent(output, margin))
    if error:
        print(indent(click.style(error, fg="red"), margin))
    if error_code is not None:
        print(click.style(f"{margin}Return code: {error_code}", fg="yellow"))


def run_cmd(*args):
    """Run a system command, print output and return results.

    Relies on robust ``run`` function implemented in xbar plugin.
    """
    code, output, error = xbar_run(*args)
    print_cli_output(args, output, error, code)
    return code, output, error


@pytest.fixture
def runner():
    runner = CliRunner(mix_stderr=False)
    with runner.isolated_filesystem():
        yield runner


@pytest.fixture(autouse=True)
def mock_conf_location(tmp_path, monkeypatch):
    """Patch the default config file location to force it within pytest's isolated temporary filesystem.

    That patch applies to all unittests.
    """

    def _mock_conf_location():
        return tmp_path.joinpath(config.DEFAULT_CONF_NAME).resolve()

    monkeypatch.setattr(config, "default_conf_path", _mock_conf_location)


@pytest.fixture
def invoke(runner):
    """Executes Click's CLI, print output and return results."""

    def _run(*args, color=False):
        # We allow for nested iterables and None values as args for
        # convenience. We just need to flatten and filters them out.
        args = list(filter(None.__ne__, flatten(args)))
        if args:
            assert same(map(type, args), str)

        # Forces logger reset before each CLI invokation as it seems the
        # @ctx.call_on_close decorator in cli.py is not enough to clean up some
        # re-entrant calls in the test suite.
        reset_logger()

        # Force default_map reset between calls to prevent initial context to be polluted by previous tests.
        result = runner.invoke(cli, args, color=color, default_map={})

        # Strip colors out of results.
        result.stdout_bytes = strip_ansi(result.stdout_bytes)
        result.stderr_bytes = strip_ansi(result.stderr_bytes)

        print_cli_output(
            [CLI_NAME] + args, result.output, result.stderr, result.exit_code
        )

        if result.exception:
            print(ExceptionInfo.from_exc_info(*result.exc_info).get_formatted())

        return result

    return _run


@pytest.fixture(scope="class")
def subcmd():
    """Fixture used in ``test_cli_*.py`` files to set the sub-command in all CLI
    calls.

    Must returns a string or an iterable of strings. Defaults to ``None``, which
    allows tests relying on this fixture to selectively skip running.
    """
    return None


@pytest.fixture
def create_toml(tmp_path):
    """A generic fixture to produce a temporary TOML file."""

    def _create_toml(filename, content):
        """Create a fake TOML file."""
        assert isinstance(content, str)

        if isinstance(filename, str):
            toml_path = tmp_path.joinpath(filename)
        else:
            assert isinstance(filename, Path)
            toml_path = filename.resolve()

        # Create the missing folder structure, like "mkdir -p" does.
        toml_path.parent.mkdir(parents=True, exist_ok=True)
        toml_path.write_text(dedent(content).strip())

        return toml_path

    return _create_toml
