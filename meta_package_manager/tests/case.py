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

import os
import unittest

from boltons.tbutils import ExceptionInfo
from click.testing import CliRunner

from ..bitbar import run
from ..cli import cli
from ..platform import is_linux, is_macos, is_windows


def skip_destructive():
    """ Decorator to skip a test unless destructive mode is allowed.

    Destructive mode is activated by the presence of a ``DESTRUCTIVE_TESTS``
    environment variable set to ``True``.
    """
    destructive_tests = os.environ.get('DESTRUCTIVE_TESTS', False) in [True, 1]
    if destructive_tests:
        # Destructive mode is ON. Let the test run anyway.
        return lambda func: func
    return unittest.skip("Destructive tests not allowed.")


def unless_linux():
    """ Decorator to skip a test unless it is run on a Linux system. """
    if is_linux():
        # Run the test.
        return lambda func: func
    return unittest.skip("Test requires Linux.")


def unless_macos():
    """ Decorator to skip a test unless it is run on a macOS system. """
    if is_macos():
        # Run the test.
        return lambda func: func
    return unittest.skip("Test requires macOS.")


def unless_windows():
    """ Decorator to skip a test unless it is run on a Windows system. """
    if is_windows():
        # Run the test.
        return lambda func: func
    return unittest.skip("Test requires Windows.")


class ManagerTestCase(unittest.TestCase):

    # Hard-coded list of all supported manager IDs.
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
        'yarn'])


class CLITestCase(ManagerTestCase):

    """ Utilities and helpers to easely write unit-tests. """

    def __init__(self, *args, **kwargs):
        """ Force running all unittests within an isolated filesystem.

        Intercepts `__init__()` to have an oportunity to decorate manually the
        whole `run()` method itself, so each test method and calls to `setUp()`
        are wrap by the isolated filesystem decoartor. See:
        https://github.com/python/cpython/blob/v3.6.0/Lib/unittest/case.py#L648-L649
        """
        super(CLITestCase, self).__init__(*args, **kwargs)

        self.runner = CliRunner()

        run_method = self.run
        decorated_run = self.runner.isolated_filesystem()(run_method)
        self.run = decorated_run

    def print_cli_output(self, cmd, output):
        """ Simulate CLI output.

        Used to print debug traces in test suites.
        """
        print(u"$ {}".format(' '.join(cmd)))
        print(output)

    def run_cmd(self, *args):
        """ Run a system command, print output and return results. """
        code, output, error = run(*args)

        self.print_cli_output(args, output)

        # Print some more debug info.
        print("Return code: {}".format(code))
        if error:
            print(error)

        return code, output, error

    def invoke(self, *args):
        """ Executes Click's CLI, print output and return results. """
        result = self.runner.invoke(cli, args)

        self.print_cli_output(['mpm'] + list(args), result.output)

        # Print some more debug info.
        print(result)
        if result.exception:
            print(ExceptionInfo.from_exc_info(
                *result.exc_info).get_formatted())

        return result
