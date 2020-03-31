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
from pathlib import PurePath, Path

from ..managers import pool
from ..platform import OS_DEFINITIONS
from ..version import TokenizedString
from .case import unless_linux, unless_macos, unless_windows


class TestManagerDefinitions(unittest.TestCase):

    """ Test the form and data types returned by all package managers. """

    def test_manager_count(self):
        """ Check all implemented package managers are accounted for. """
        self.assertEqual(len(pool()), 13)

    def test_ascii_id(self):
        """ All package manager IDs should be short ASCII strings. """
        for manager_id, manager in pool().items():
            self.assertRegex(manager_id, r'[a-z0-9]+')
            self.assertEqual(manager_id, manager.id)
            self.assertIsInstance(manager.id, str)

    def test_name(self):
        """ Check all managers have a name. """
        for manager in pool().values():
            self.assertIsInstance(manager.name, str)
            self.assertRegex(manager.name, r'[a-zA-Z0-9\' ]+')

    def test_platforms(self):
        """ Check that definitions returns supported platforms as a frozenset.
        """
        for manager in pool().values():
            self.assertIsInstance(manager.platforms, frozenset)
            self.assertTrue(manager.platforms.issubset(OS_DEFINITIONS))

    def test_cli_name_type(self):
        """ Check the pointed CLI name and path are file-system compatible. """
        for manager in pool().values():
            self.assertEqual(PurePath(manager.cli_name).name, manager.cli_name)

    def test_virtual(self):
        """ Check the manager as a defined virtual property. """
        for manager in pool().values():
            self.assertIsInstance(manager.virtual, bool)

    def test_cli_path(self):
        for manager in pool().values():
            if manager.cli_path is not None:
                self.assertIsInstance(manager.cli_path, str)
                parsed_path = Path(manager.cli_path)
                self.assertTrue(parsed_path.is_absolute())
                self.assertFalse(parsed_path.is_reserved())
                self.assertEqual(parsed_path.name, manager.cli_name)
                self.assertTrue(parsed_path.is_file())

    def test_global_args_type(self):
        """ Check that definitions returns CLI args as a list of strings. """
        for manager in pool().values():
            self.assertIsInstance(manager.global_args, list)
            for arg in manager.global_args:
                self.assertIsInstance(arg, str)

    def test_requirement(self):
        """ Each manager is required to specify a minimal version. """
        for manager in pool().values():
            self.assertIsInstance(manager.requirement, str)
            self.assertRegex(manager.requirement, r'[0-9\.]+')
            # Check the string provided is lossless once passed through
            # TokenizedString.
            self.assertEqual(
                str(TokenizedString(manager.requirement)), manager.requirement)

    def test_get_version(self):
        """ Check that method parsing the CLI version returns a string. """
        for manager in pool().values():
            self.assertIsInstance(manager.get_version, MethodType)
            if manager.executable:
                if manager.get_version() is not None:
                    self.assertIsInstance(
                        manager.get_version(), TokenizedString)

    def test_version(self):
        for manager in pool().values():
            if manager.version is not None:
                self.assertIsInstance(manager.version, TokenizedString)

    def test_supported(self):
        for manager in pool().values():
            self.assertIsInstance(manager.supported, bool)

    def test_executable(self):
        for manager in pool().values():
            self.assertIsInstance(manager.executable, bool)

    def test_fresh(self):
        for manager in pool().values():
            self.assertIsInstance(manager.fresh, bool)

    def test_available(self):
        for manager in pool().values():
            self.assertIsInstance(manager.available, bool)

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
                    self.assertSetEqual(set(pkg), set([
                        'id', 'name', 'installed_version']))
                    self.assertIsInstance(pkg['id'], str)
                    self.assertIsInstance(pkg['name'], str)
                    if pkg['installed_version'] is not None:
                        self.assertIsInstance(
                            pkg['installed_version'], TokenizedString)

    def test_search_type(self):
        """ Check that all search operations returns a dict of dicts. """
        for manager in pool().values():
            if manager.available:
                matches = manager.search('python')
                self.assertIsInstance(matches, dict)
                for pkg in matches.values():
                    self.assertIsInstance(pkg, dict)
                    self.assertSetEqual(set(pkg), set([
                        'id', 'name', 'latest_version', 'exact']))
                    self.assertIsInstance(pkg['id'], str)
                    self.assertIsInstance(pkg['name'], str)
                    if pkg['latest_version'] is not None:
                        self.assertIsInstance(
                            pkg['latest_version'], TokenizedString)
                    self.assertIsInstance(pkg['exact'], bool)

    def test_outdated_type(self):
        """ Check that all outdated operations returns a dict of dicts. """
        for manager in pool().values():
            if manager.available:
                self.assertIsInstance(manager.outdated, dict)
                for pkg in manager.outdated.values():
                    self.assertIsInstance(pkg, dict)
                    self.assertSetEqual(set(pkg), set([
                        'id', 'name', 'installed_version', 'latest_version']))
                    self.assertIsInstance(pkg['id'], str)
                    self.assertIsInstance(pkg['name'], str)
                    if pkg['installed_version'] is not None:
                        self.assertIsInstance(
                            pkg['installed_version'], TokenizedString)
                    self.assertIsInstance(
                        pkg['latest_version'], TokenizedString)

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
