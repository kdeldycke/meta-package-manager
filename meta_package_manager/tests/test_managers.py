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

import unittest
from types import MethodType

from ..managers import pool
from ..platform import OS_DEFINITIONS
from ..version import TokenizedString
from .case import unless_linux, unless_macos, unless_windows


class TestManagerDefinitions(unittest.TestCase):

    """ Test the definition of all package managers. """

    def test_ascii_id(self):
        """ All package manager IDs should be short ASCII strings. """
        for manager_id in pool():
            self.assertRegex(manager_id, r'[a-z0-9]+')

    def test_number(self):
        """ Check all implemented package managers are accounted for. """
        self.assertEqual(len(pool()), 13)

    def test_platforms_type(self):
        """ Check that definitions returns supported platforms as a frozenset.
        """
        for manager in pool().values():
            self.assertIsInstance(manager.platforms, frozenset)

    def test_platforms_values(self):
        """ Check that definitions returns platforms with a registered label.
        """
        for manager in pool().values():
            self.assertTrue(manager.platforms.issubset(OS_DEFINITIONS))

    def test_cli_path_type(self):
        """ Check that definitions returns the CLI path as a string. """
        for manager in pool().values():
            self.assertIsInstance(manager.cli_name, str)
            if manager.cli_path is not None:
                self.assertIsInstance(manager.cli_path, str)

    def test_cli_args_type(self):
        """ Check that definitions returns CLI args as a list. """
        for manager in pool().values():
            self.assertIsInstance(manager.cli_args, list)

    def test_cli_type(self):
        """ Check that all methods returning a CLI is a list. """
        for manager in pool().values():
            self.assertIsInstance(
                manager.upgrade_cli('dummy_package_id'), list)

            # Upgrade-all CLI are allowed to raise a particular error.
            try:
                result = manager.upgrade_all_cli()
            except Exception as excpt:
                self.assertIsInstance(excpt, NotImplementedError)
            else:
                self.assertIsInstance(result, list)

    def test_installed_type(self):
        """ Check that all installed operations returns a dict of dicts. """
        for manager in pool().values():
            if manager.available:
                self.assertIsInstance(manager.installed, dict)
                for pkg in manager.installed.values():
                    self.assertIsInstance(pkg, dict)
                    self.assertEqual(set(pkg), set([
                        'id', 'name', 'installed_version']))
                    self.assertIsInstance(pkg['id'], str)
                    self.assertIsInstance(pkg['name'], str)
                    if pkg['installed_version'] is not None:
                        self.assertIsInstance(
                            pkg['installed_version'], (str, TokenizedString))

    def test_search_type(self):
        """ Check that all search operations returns a dict of dicts. """
        for manager in pool().values():
            if manager.available:
                matches = manager.search('python')
                self.assertIsInstance(matches, dict)
                for pkg in matches.values():
                    self.assertIsInstance(pkg, dict)
                    self.assertEqual(set(pkg), set([
                        'id', 'name', 'latest_version', 'exact']))
                    self.assertIsInstance(pkg['id'], str)
                    self.assertIsInstance(pkg['name'], str)
                    if pkg['latest_version'] is not None:
                        self.assertIsInstance(
                            pkg['latest_version'], str)
                    self.assertIsInstance(pkg['exact'], bool)

    def test_outdated_type(self):
        """ Check that all outdated operations returns a dict of dicts. """
        for manager in pool().values():
            if manager.available:
                self.assertIsInstance(manager.outdated, dict)
                for pkg in manager.outdated.values():
                    self.assertIsInstance(pkg, dict)
                    self.assertEqual(set(pkg), set([
                        'id', 'name', 'installed_version', 'latest_version']))
                    self.assertIsInstance(pkg['id'], str)
                    self.assertIsInstance(pkg['name'], str)
                    if pkg['installed_version'] is not None:
                        self.assertIsInstance(
                            pkg['installed_version'], str)
                    self.assertIsInstance(pkg['latest_version'], str)

    def test_sync_type(self):
        """ Check that sync operation return nothing. """
        for manager in pool().values():
            if manager.available:
                self.assertIsInstance(manager.sync, MethodType)
                self.assertIsNone(manager.sync())

    def test_cleanup_type(self):
        """ Check that cleanup operation return nothing. """
        for manager in pool().values():
            if manager.available:
                self.assertIsInstance(manager.cleanup, MethodType)
                self.assertIsNone(manager.cleanup())


class TestManagerPlatform(unittest.TestCase):

    @unless_macos()
    def test_macos(self):
        supported_managers = {m.id for m in pool().values() if m.supported}
        self.assertSetEqual(supported_managers, set([
            'apm', 'brew', 'cask', 'composer', 'gem', 'mas', 'npm',
            'pip2', 'pip3', 'yarn']))

    @unless_linux()
    def test_linux(self):
        supported_managers = {m.id for m in pool().values() if m.supported}
        self.assertSetEqual(supported_managers, set([
            'apm', 'apt', 'composer', 'gem', 'npm', 'pip2', 'pip3',
            'flatpak', 'opkg', 'yarn']))

    @unless_windows()
    def test_windows(self):
        supported_managers = {m.id for m in pool().values() if m.supported}
        self.assertSetEqual(supported_managers, set([
            'apm', 'composer', 'gem', 'npm', 'pip2', 'pip3', 'yarn']))
