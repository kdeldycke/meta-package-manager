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

import re
from pathlib import Path, PurePath
from types import MethodType

from ..managers import pool
from ..platform import OS_DEFINITIONS
from ..version import TokenizedString
from .conftest import MANAGER_IDS

""" Test the structure, data and types returned by all package managers. """


def test_manager_count():
    """ Check all implemented package managers are accounted for. """
    assert len(pool()) == 13
    assert len(pool()) == len(MANAGER_IDS)
    assert MANAGER_IDS == set(pool())


def test_cached_pool():
    assert pool() == pool()
    assert pool() is pool()


def test_sorted_pool():
    assert list(pool()) == sorted([m.id for m in pool().values()])


def test_ascii_id():
    """ All package manager IDs should be short ASCII strings. """
    for manager_id, manager in pool().items():
        assert manager_id
        assert isinstance(manager_id, str)
        assert manager_id.isascii()
        assert manager_id.isalnum()
        assert manager_id.islower()
        assert manager_id == manager.id


def test_name():
    """ Check all managers have a name. """
    name_matcher = re.compile(r"[a-zA-Z0-9\' ]+")
    for manager in pool().values():
        assert manager.name
        assert isinstance(manager.name, str)
        assert name_matcher.match(manager.name)
    # Names are unique.
    assert len({m.name for m in pool().values()}) == len(MANAGER_IDS)


def test_platforms():
    """Check that definitions returns supported platforms as a frozenset."""
    for manager in pool().values():
        assert manager.platforms
        assert isinstance(manager.platforms, frozenset)
        assert manager.platforms.issubset(OS_DEFINITIONS)


def test_cli_name_type():
    """ Check the pointed CLI name and path are file-system compatible. """
    for manager in pool().values():
        assert manager.cli_name
        assert isinstance(manager.cli_name, str)
        assert manager.cli_name.isalnum()
        assert PurePath(manager.cli_name).name == manager.cli_name


def test_virtual():
    """ Check the manager as a defined virtual property. """
    for manager in pool().values():
        assert isinstance(manager.virtual, bool)


def test_cli_search_path():
    for manager in pool().values():
        assert isinstance(manager.cli_search_path, list)
        assert len(set(manager.cli_search_path)) == len(manager.cli_search_path)
        for search_path in manager.cli_search_path:
            assert isinstance(search_path, str)
            path_obj = Path(search_path).resolve()
            assert path_obj.is_absolute()
            assert not path_obj.is_reserved()
            if path_obj.exists():
                assert path_obj.is_file() or path_obj.is_dir()


def test_cli_path():
    for manager in pool().values():
        if manager.cli_path is not None:
            assert isinstance(manager.cli_path, Path)
            assert manager.cli_path.is_absolute()
            assert not manager.cli_path.is_reserved()
            assert manager.cli_path.is_file()


def test_global_args_type():
    """ Check that definitions returns CLI args as a list of strings. """
    arg_matcher = re.compile(r"[a-zA-Z0-9-]+")
    for manager in pool().values():
        assert isinstance(manager.global_args, list)
        for arg in manager.global_args:
            assert arg
            assert isinstance(arg, str)
            assert arg_matcher.match(arg)


def test_requirement():
    """ Each manager is required to specify a minimal version. """
    req_matcher = re.compile(r"[0-9\.]+")
    for manager in pool().values():
        assert isinstance(manager.requirement, str)
        assert req_matcher.match(manager.requirement)
        # Check provided string is lossless once passed via TokenizedString.
        assert str(TokenizedString(manager.requirement)) == manager.requirement


def test_get_version():
    """ Check that method parsing the CLI version returns a string. """
    for manager in pool().values():
        assert isinstance(manager.get_version, MethodType)
        if manager.executable:
            if manager.get_version() is not None:
                assert isinstance(manager.get_version(), TokenizedString)


def test_version():
    for manager in pool().values():
        if manager.version is not None:
            assert isinstance(manager.version, TokenizedString)


def test_supported():
    for manager in pool().values():
        assert isinstance(manager.supported, bool)


def test_executable():
    for manager in pool().values():
        assert isinstance(manager.executable, bool)


def test_fresh():
    for manager in pool().values():
        assert isinstance(manager.fresh, bool)


def test_available():
    for manager in pool().values():
        assert isinstance(manager.available, bool)


def test_cli_type():
    """ Check that all methods returning a CLI is a list. """
    for manager in pool().values():
        assert isinstance(manager.upgrade_cli("dummy_package_id"), list)

        # Upgrade-all CLI are allowed to raise a particular error.
        try:
            result = manager.upgrade_all_cli()
        except Exception as excpt:
            assert isinstance(excpt, NotImplementedError)
        else:
            assert isinstance(result, list)


def test_installed_type():
    """ Check that all installed operations returns a dict of dicts. """
    for manager in pool().values():
        if manager.available:
            assert isinstance(manager.installed, dict)
            for pkg in manager.installed.values():
                assert isinstance(pkg, dict)
                assert set(pkg) == {"id", "name", "installed_version"}
                assert isinstance(pkg["id"], str)
                assert isinstance(pkg["name"], str)
                if pkg["installed_version"] is not None:
                    assert isinstance(pkg["installed_version"], TokenizedString)


def test_search_type():
    """ Check that all search operations returns a dict of dicts. """
    for manager in pool().values():
        if manager.available:
            matches = manager.search("python", extended=True, exact=False)
            assert isinstance(matches, dict)
            for pkg in matches.values():
                assert isinstance(pkg, dict)
                assert set(pkg) == {"id", "name", "latest_version"}
                assert isinstance(pkg["id"], str)
                assert isinstance(pkg["name"], str)
                if pkg["latest_version"] is not None:
                    assert isinstance(pkg["latest_version"], TokenizedString)


def test_outdated_type():
    """ Check that all outdated operations returns a dict of dicts. """
    for manager in pool().values():
        if manager.available:
            assert isinstance(manager.outdated, dict)
            for pkg in manager.outdated.values():
                assert isinstance(pkg, dict)
                assert set(pkg) == {"id", "name", "installed_version", "latest_version"}
                assert isinstance(pkg["id"], str)
                assert isinstance(pkg["name"], str)
                if pkg["installed_version"] is not None:
                    assert isinstance(pkg["installed_version"], TokenizedString)
                assert isinstance(pkg["latest_version"], TokenizedString)


def test_sync_type():
    """ Check that sync operation return nothing. """
    for manager in pool().values():
        if manager.available:
            assert isinstance(manager.sync, MethodType)
            assert manager.sync() is None


def test_cleanup_type():
    """ Check that cleanup operation return nothing. """
    for manager in pool().values():
        if manager.available:
            assert isinstance(manager.cleanup, MethodType)
            assert manager.cleanup() is None
