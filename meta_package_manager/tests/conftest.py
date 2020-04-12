# -*- coding: utf-8 -*-
#
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

import pytest
from boltons.iterutils import flatten
from boltons.tbutils import ExceptionInfo
from click.testing import CliRunner

from ..bitbar import run as bitbar_run
from ..cli import cli
from ..platform import is_linux, is_macos, is_windows

""" Fixtures, configuration and helpers for tests. """


MANAGER_IDS = frozenset([
    'apm',
    'apt',
    'brew',
    'cask',
    'composer',
    'flatpak',
    'gem',
    'mas',
    'npm',
    'opkg',
    'pip2',
    'pip3',
    'snap',
    'yarn'])
""" Hard-coded list of all supported manager IDs. """


destructive = pytest.mark.skipif(
    bool(os.environ.get('DESTRUCTIVE_TESTS', False) not in [
        True, 1, 'True', 'true', '1']),
    reason="destructive tests")
""" Pytest mark to skip a test unless destructive mode is allowed.

Destructive mode is activated by the presence of a ``DESTRUCTIVE_TESTS``
environment variable set to ``True``.

.. todo:

    Test destructive test assessment.
"""


unless_linux = pytest.mark.skipif(
    not is_linux(), reason="Linux required")
""" Pytest mark to skip a test unless it is run on a Linux system. """


unless_macos = pytest.mark.skipif(
    not is_macos(), reason="macOS required")
""" Pytest mark to skip a test unless it is run on a macOS system. """


unless_windows = pytest.mark.skipif(
    not is_windows(), reason="Windows required")
""" Pytest mark to skip a test unless it is run on a Windows system. """


def print_cli_output(cmd, output):
    """ Simulate CLI output. Used to print debug traces in test results. """
    print(u"\n$ {}".format(' '.join(cmd)))
    print(output)


def run_cmd(*args):
    """ Run a system command, print output and return results.

    Relies on robust ``run`` function implemented in BitBar plugin.
    """
    code, output, error = bitbar_run(*args)

    print_cli_output(args, output)

    # Print some more debug info.
    print("Return code: {}".format(code))
    if error:
        print(error)

    return code, output, error


@pytest.fixture(autouse=True, scope="module")
def runner(request):
    runner = CliRunner()
    with runner.isolated_filesystem():
        yield runner


# XXX Try reduce fixture scopr to function?
@pytest.fixture(scope="module")
def invoke(runner, *args):
    """ Executes Click's CLI, print output and return results. """

    def run_run(*args):
        # TODO: Add that flatten trick in Base.run_cli() utils? Should simplify
        # the writing of *args & others + []
        args = flatten(args)

        assert isinstance(args, list)
        if args:
            assert set(map(type, args)) == {str}

        result = runner.invoke(cli, args)

        print_cli_output(['mpm'] + args, result.output)

        # Print some more debug info.
        print(result)
        if result.exception:
            print(ExceptionInfo.from_exc_info(
                *result.exc_info).get_formatted())

        return result

    return run_run


@pytest.fixture
def subcommand():
    """ Fixture used in `test_cli_*.py` files to set the sub-command in all CLI
    calls.

    Must returns a string or an iterable of strings. Defaults to `None`, which
    allows tests relying on this fixture to selectively skip running.
    """
    return None
