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

import ast
import inspect
import re
from pathlib import Path, PurePath
from string import ascii_letters, ascii_lowercase, digits

import pytest
from boltons.iterutils import unique
from boltons.urlutils import URL
from click_extra.platforms import ALL_PLATFORMS, Platform

from meta_package_manager.base import Operations, PackageManager
from meta_package_manager.cli import XKCD_MANAGER_ORDER
from meta_package_manager.pool import pool
from meta_package_manager.version import TokenizedString

from .conftest import all_managers, manager_classes

""" Test the structure, data and types returned by all package managers.

This test suite try to automate most of the basic reviewing work for the addition of
new package manager definitions.
"""


def test_xkcd_set():
    assert len(unique(XKCD_MANAGER_ORDER)) == len(XKCD_MANAGER_ORDER)
    assert set(pool.all_manager_ids).issuperset(XKCD_MANAGER_ORDER)


@all_managers
def test_deprecated(manager):
    if manager.deprecation_url is not None:
        location = URL(manager.deprecation_url)
        assert location
        assert location.scheme.lower() in ("http", "https")
        assert manager.deprecated is True


@all_managers
def test_ascii_id(manager):
    """All package manager IDs should be short ASCII strings."""
    assert manager.id
    assert manager.id.isascii()
    assert set(manager.id).issubset(ascii_lowercase + digits + "-")


@all_managers
def test_name(manager):
    """Check all managers have a name."""
    assert manager.name
    assert set(manager.name).issubset(ascii_letters + digits + "' ")


def test_unique_names():
    assert len({m.name for m in pool.values()}) == len(pool.all_manager_ids)


@all_managers
def test_homepage_url(manager):
    assert manager.homepage_url
    location = URL(manager.homepage_url)
    assert location
    assert location.scheme.lower() in ("http", "https")


@all_managers
def test_platforms(manager):
    """Check platforms is normalized as a frozenset."""
    assert manager.platforms
    assert isinstance(manager.platforms, frozenset)
    assert all(isinstance(p, Platform) for p in manager.platforms)
    assert ALL_PLATFORMS.issuperset(manager.platforms)


@all_managers
def test_requirement(manager):
    """Each manager is required to specify a minimal version or ``None``."""
    if manager.requirement is not None:
        assert set(manager.requirement).issubset(digits + ".")
        # Check provided string is lossless once passed via TokenizedString.
        assert str(TokenizedString(manager.requirement)) == manager.requirement


@all_managers
def test_cli_names_type(manager):
    """Check the pointed CLI name and path are file-system compatible."""
    assert manager.cli_names
    for name in manager.cli_names:
        assert name.isalnum()
        assert PurePath(name).name == name


@all_managers
def test_cli_search_path(manager):
    assert len(set(manager.cli_search_path)) == len(manager.cli_search_path)
    for search_path in manager.cli_search_path:
        path_obj = Path(search_path).resolve()
        assert path_obj.is_absolute()
        assert not path_obj.is_reserved()
        if path_obj.exists():
            assert path_obj.is_file() or path_obj.is_dir()


@all_managers
def test_extra_env_type(manager):
    """Check that definitions environment variables as a dict of strings."""
    if manager.extra_env:
        for key, value in manager.extra_env.items():
            for item in (key, value):
                assert item
                assert set(item).issubset(ascii_letters + digits + "_-")


@all_managers
def test_global_args_type(manager):
    """Check that definitions returns CLI args as a list of non-empty strings."""
    for global_args in (manager.pre_cmds, manager.pre_args, manager.post_args):
        assert all(global_args)
        for arg in global_args:
            assert set(arg).issubset(ascii_letters + digits + "-=+")


@all_managers
def test_version_cli_options(manager):
    """Version CLI options must be a list of non empty strings."""
    assert all(manager.version_cli_options)


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


@pytest.mark.parametrize(
    ("query", "query_parts"),
    (
        ("cli-l-cli", {"cli", "l"}),
        ("ab12--cd34", {"ab12", "cd34"}),
        ("123/extra.34", {"123", "extra", "34"}),
        ("AB ab", {"AB", "ab"}),
    ),
)
def test_query_parts(query, query_parts):
    assert PackageManager.query_parts(query) == query_parts


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
@manager_classes  # type: ignore[operator]
def test_content_order(manager_class):
    """Lint each package manager definition file to check its code structure is the same
    as the canonical PackageManager base class."""
    # Collect in order the IDs of all properties (ast.Assign) and functions in
    # the class.
    collected_props = []

    klass_tree = ast.parse(inspect.getsource(manager_class))
    for node in klass_tree.body:
        if isinstance(node, ast.Assign):
            collected_props.extend([t.id for t in node.targets])
        if isinstance(node, ast.FunctionDef):
            collected_props.append(node.name)

    enforced_props = tuple(p for p in collected_props if p in props_ref)
    expected_order = tuple(p for p in props_ref if p in collected_props)
    assert enforced_props == expected_order
