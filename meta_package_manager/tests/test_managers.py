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

from __future__ import annotations

import ast
import inspect
import re
import types
from operator import attrgetter
from pathlib import Path, PurePath
from string import ascii_letters, ascii_lowercase, digits

import pytest
from boltons.iterutils import unique
from boltons.urlutils import URL
from click_extra.platform import OS_DEFINITIONS
from click_extra.tests.conftest import destructive

from ..base import Operations, Package, PackageManager
from ..cli import XKCD_MANAGER_ORDER
from ..pool import pool
from ..version import TokenizedString

""" Test the structure, data and types returned by all package managers.

This test suite try to automate most of the basic reviewing work for the addition of
new package manager definitions.
"""

# Parametrization decorators.
all_managers = pytest.mark.parametrize("manager", pool.values(), ids=attrgetter("id"))
available_managers = pytest.mark.parametrize(
    "manager", tuple(m for m in pool.values() if m.available), ids=attrgetter("id")
)


def test_xkcd_set():
    assert len(unique(XKCD_MANAGER_ORDER)) == len(XKCD_MANAGER_ORDER)
    assert set(pool.all_manager_ids).issuperset(XKCD_MANAGER_ORDER)


@all_managers
def test_deprecated(manager):
    assert isinstance(manager.deprecated, bool)
    if manager.deprecation_url is not None:
        assert isinstance(manager.deprecation_url, str)
        location = URL(manager.deprecation_url)
        assert location
        assert location.scheme.lower() in ("http", "https")
        assert manager.deprecated is True


@pytest.mark.parametrize("manager_id,manager", pool.items())
def test_ascii_id(manager_id, manager):
    """All package manager IDs should be short ASCII strings."""
    assert manager_id
    assert isinstance(manager_id, str)
    assert manager_id.isascii()
    assert set(manager_id).issubset(ascii_lowercase + digits + "-")
    assert manager_id == manager.id


@all_managers
def test_name(manager):
    """Check all managers have a name."""
    assert manager.name
    assert isinstance(manager.name, str)
    assert set(manager.name).issubset(ascii_letters + digits + "' ")


def test_unique_names():
    assert len({m.name for m in pool.values()}) == len(pool.all_manager_ids)


@all_managers
def test_homepage_url(manager):
    assert manager.homepage_url
    assert isinstance(manager.homepage_url, str)
    location = URL(manager.homepage_url)
    assert location
    assert location.scheme.lower() in ("http", "https")


@all_managers
def test_platforms(manager):
    """Check that definitions returns supported platforms as a frozenset."""
    assert manager.platforms
    assert isinstance(manager.platforms, frozenset)
    assert manager.platforms.issubset(OS_DEFINITIONS)


@all_managers
def test_requirement(manager):
    """Each manager is required to specify a minimal version or ``None``."""
    if manager.requirement is not None:
        assert isinstance(manager.requirement, str)
        assert set(manager.requirement).issubset(digits + ".")
        # Check provided string is lossless once passed via TokenizedString.
        assert str(TokenizedString(manager.requirement)) == manager.requirement


@all_managers
def test_cli_names_type(manager):
    """Check the pointed CLI name and path are file-system compatible."""
    assert manager.cli_names
    assert isinstance(manager.cli_names, tuple)
    for name in manager.cli_names:
        assert isinstance(name, str)
        assert name.isalnum()
        assert PurePath(name).name == name


@all_managers
def test_virtual(manager):
    """Check the manager as a defined virtual property."""
    assert isinstance(manager.virtual, bool)


@all_managers
def test_cli_search_path(manager):
    assert isinstance(manager.cli_search_path, tuple)
    assert len(set(manager.cli_search_path)) == len(manager.cli_search_path)
    for search_path in manager.cli_search_path:
        assert isinstance(search_path, str)
        path_obj = Path(search_path).resolve()
        assert path_obj.is_absolute()
        assert not path_obj.is_reserved()
        if path_obj.exists():
            assert path_obj.is_file() or path_obj.is_dir()


@all_managers
def test_extra_env_type(manager):
    """Check that definitions environment variables as a dict of strings."""
    assert manager.extra_env is None or isinstance(manager.extra_env, dict)
    if manager.extra_env:
        for key, value in manager.extra_env.items():
            for item in (key, value):
                assert item
                assert isinstance(item, str)
                assert set(item).issubset(ascii_letters + digits + "_-")


@all_managers
def test_global_args_type(manager):
    """Check that definitions returns CLI args as a list of strings."""
    for global_args in (manager.pre_cmds, manager.pre_args, manager.post_args):
        assert isinstance(global_args, tuple)
        for arg in global_args:
            assert arg
            assert isinstance(arg, str)
            assert set(arg).issubset(ascii_letters + digits + "-=+")


@all_managers
def test_version_cli_options(manager):
    """Version CLI options must be a list of strings or a dict of that structure."""
    assert isinstance(manager.version_cli_options, tuple)
    for arg in manager.version_cli_options:
        assert arg
        assert isinstance(arg, str)


@all_managers
def test_version_regex(manager):
    """Version regex is required.

    Check it compiles and match has a version group.
    """
    assert isinstance(manager.version_regex, str)
    regex = re.compile(manager.version_regex)
    assert "version" in regex.groupindex


@all_managers
def test_cli_path(manager):
    if manager.cli_path is not None:
        assert isinstance(manager.cli_path, Path)
        assert manager.cli_path.is_absolute()
        assert not manager.cli_path.is_reserved()
        assert manager.cli_path.is_file()


@all_managers
def test_version(manager):
    if manager.version is not None:
        assert isinstance(manager.version, TokenizedString)


@all_managers
def test_supported(manager):
    assert isinstance(manager.supported, bool)


@all_managers
def test_executable(manager):
    assert isinstance(manager.executable, bool)


@all_managers
def test_fresh(manager):
    assert isinstance(manager.fresh, bool)


@all_managers
def test_available(manager):
    assert isinstance(manager.available, bool)


@available_managers
def test_installed_type(manager):
    """All installed operations are either not implemented or returns a dict of
    dicts."""
    try:
        result = manager.installed
    except Exception as ex:
        assert isinstance(ex, NotImplementedError)
    else:
        assert isinstance(result, types.GeneratorType)
        for pkg in result:
            assert isinstance(pkg, Package)


@available_managers
def test_outdated_type(manager):
    """All outdated operations are either not implemented or returns a dict of dicts."""
    try:
        result = manager.outdated
    except Exception as ex:
        assert isinstance(ex, NotImplementedError)
    else:
        assert isinstance(result, types.GeneratorType)
        for pkg in result:
            assert isinstance(pkg, Package)


@pytest.mark.parametrize(
    "query,query_parts",
    (
        ("cli-l-cli", {"cli", "l"}),
        ("ab12--cd34", {"ab12", "cd34"}),
        ("123/extra.34", {"123", "extra", "34"}),
        ("AB ab", {"AB", "ab"}),
    ),
)
def test_query_parts(query, query_parts):
    assert PackageManager.query_parts(query) == query_parts


@available_managers
def test_search_type(manager):
    """All search operations are either not implemented or returns a generator of
    dicts."""
    try:
        matches = manager.search("python", extended=True, exact=False)
    except Exception as ex:
        assert isinstance(ex, NotImplementedError)
    else:
        assert isinstance(matches, types.GeneratorType)
        for pkg in matches:
            assert isinstance(pkg, Package)


@destructive
@available_managers
def test_install_type(manager):
    """All methods installing packages are either not implemented or returns a
    string."""
    try:
        result = manager.install("dummy_package_id")
    except Exception as ex:
        assert isinstance(ex, NotImplementedError)
    else:
        assert isinstance(result, str)


@destructive
@available_managers
def test_upgrade_all_cli_type(manager):
    """All methods returning an upgrade-all CLI are either not implemented or returns a
    tuple."""
    try:
        result = manager.upgrade_all_cli()
    except Exception as ex:
        assert isinstance(ex, NotImplementedError)
    else:
        assert isinstance(result, tuple)


@destructive
@available_managers
def test_upgrade_one_cli_type(manager):
    """All methods returning an upgrade CLI are either not implemented or returns a
    tuple."""
    try:
        result = manager.upgrade_one_cli("dummy_package_id")
    except Exception as ex:
        assert isinstance(ex, NotImplementedError)
    else:
        assert isinstance(result, tuple)


@destructive
@available_managers
def test_upgrade_type(manager):
    """All methods upgrading packages are either not implemented or returns a string."""
    try:
        result = manager.upgrade()
    except Exception as ex:
        assert isinstance(ex, NotImplementedError)
    else:
        assert isinstance(result, str)


@destructive
@available_managers
def test_remove_type(manager):
    """All methods removing packages are either not implemented or returns a string."""
    try:
        result = manager.remove("dummy_package_id")
    except Exception as ex:
        assert isinstance(ex, NotImplementedError)
    else:
        assert isinstance(result, str)


@available_managers
def test_sync_type(manager):
    """Sync operations are either not implemented or returns nothing."""
    try:
        result = manager.sync()
    except Exception as ex:
        assert isinstance(ex, NotImplementedError)
    else:
        assert result is None


@available_managers
def test_cleanup_type(manager):
    """Cleanup operations are either not implemented or returns nothing."""
    try:
        result = manager.cleanup()
    except Exception as ex:
        assert isinstance(ex, NotImplementedError)
    else:
        assert result is None


def collect_props_ref():
    """Build the canonical reference from the base class.

    We need to parse the AST so we can collect both attributes and naked type
    annotations.
    """
    tree = ast.parse(Path(inspect.getfile(PackageManager)).read_bytes())

    manager_class = None
    for n in tree.body:
        if isinstance(n, ast.ClassDef) and n.name == "PackageManager":
            manager_class = n
            break

    for node in manager_class.body:
        if isinstance(node, ast.AnnAssign):
            yield node.target.id
        if isinstance(node, ast.Assign):
            yield from [t.id for t in node.targets]
        if isinstance(node, ast.FunctionDef):
            yield node.name


props_ref = tuple(collect_props_ref())


def test_operation_order():
    """Double check operation IDs are ordered and aligned to the base manager class and
    CLI implementation."""
    direct_operation_ids = [op for op in Operations.__members__ if op != "upgrade_all"]

    base_operations = [p for p in props_ref if p in direct_operation_ids]
    assert list(direct_operation_ids) == list(base_operations)

    cli_tree = ast.parse(Path(__file__).parent.joinpath("../cli.py").read_bytes())
    implemented_operations = [
        n.name
        for n in cli_tree.body
        if isinstance(n, ast.FunctionDef) and n.name in direct_operation_ids
    ]
    assert list(direct_operation_ids) == list(implemented_operations)


# Check the code of each file registered in the pool.
@pytest.mark.parametrize("manager_file", pool.manager_files, ids=attrgetter("name"))
def test_content_order(manager_file):
    """Lint each package manager definition file to check its code structure is the same
    as the canonical PackageManager base class."""

    tree = ast.parse(manager_file.read_bytes())

    # Analyse each class.
    for klass in (n for n in tree.body if isinstance(n, ast.ClassDef)):

        # Collect in order the IDs of all properties (ast.Assign) and functions in
        # the class.
        collected_props = []
        for node in klass.body:
            if isinstance(node, ast.Assign):
                collected_props.extend([t.id for t in node.targets])
            if isinstance(node, ast.FunctionDef):
                collected_props.append(node.name)

        enforced_props = tuple(p for p in collected_props if p in props_ref)
        expected_order = tuple(p for p in props_ref if p in collected_props)
        assert enforced_props == expected_order
