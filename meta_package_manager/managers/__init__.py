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

""" Registration, indexing and cache of package manager definitions. """

import inspect
from collections import OrderedDict
from importlib import import_module
from pathlib import Path

from boltons.cacheutils import LRI, cached

from .. import logger
from ..base import PackageManager


# Cache the global pool of registered manager definitions to speed-up lookups.
@cached(LRI(max_size=1))
def pool():
    """Search for package manager definitions locally and store them into an
    internal register.

    Is considered valid package manager, definitions classes which:
        1 - are sub-classes of PackageManager, and
        2 - are located in files at the same level or below this one, and
        3 - are not virtual (i.e. have a non null `cli_names` property).

    Returns an `OrderedDict` sorted by manager's ID.
    """
    register = {}

    for py_file in Path(__file__).parent.glob("*.py"):
        logger.debug(f"Search manager definitions in {py_file}")
        module = import_module(f".{py_file.stem}", package=__package__)

        for _, klass in inspect.getmembers(module, inspect.isclass):
            if issubclass(klass, PackageManager) and not klass.virtual:
                logger.debug(f"Found {klass!r}")
                manager = klass()
                register[manager.id] = manager
            else:
                logger.debug(f"{klass!r} is not a valid manager definition")

    # Sort pool entries by ID.
    # TODO: propose an OrderedFrozenDict in boltons and use it here.
    return OrderedDict(sorted(register.items()))


# Pre-compute all sorts of constants.

ALL_MANAGER_IDS = frozenset(pool())
""" All recognized manager IDs. """

DEFAULT_MANAGER_IDS = frozenset({m.id for m in pool().values() if m.supported})
""" All manager IDs supported on the current platform. """

UNSUPPORTED_MANAGER_IDS = frozenset(ALL_MANAGER_IDS - DEFAULT_MANAGER_IDS)
""" All manager IDs unsupported on the current platform. """


def select_managers(
    keep=None, drop=None, drop_unsupported=True, drop_inactive=True, **kwargs
):
    """ "Utility method to extract a subset of the manager pool based on selection and exclusion criterion.

    By default, all managers are selected.

    kwargs are fed to the manager objects from the pool to set some options.

    Returns a list of manager objects sorted by IDs.
    """
    selected_ids = DEFAULT_MANAGER_IDS if drop_unsupported else ALL_MANAGER_IDS

    if not keep:
        keep = selected_ids
    if not drop:
        drop = set()
    assert isinstance(keep, (set, frozenset, tuple, list))
    assert isinstance(drop, (set, frozenset, tuple, list))

    # Only keeps the subset selected by the user.
    selected_ids = selected_ids.intersection(keep)
    # Remove managers excluded by the user.
    selected_ids = selected_ids.difference(drop)

    selected_managers = [pool()[mid] for mid in sorted(selected_ids)]

    # List of recognized manager options.
    option_ids = {"stop_on_error", "ignore_auto_updates", "dry_run"}
    assert option_ids.issuperset(kwargs)
    # Apply manager-level options.
    for m_obj in selected_managers:
        for param, value in kwargs.items():
            assert hasattr(m_obj, param)
            setattr(m_obj, param, value)

    if not drop_inactive:
        return selected_managers

    # Pre-filters inactive managers.
    def keep_available(manager):
        if manager.available:
            return True
        logger.warning(f"Skip unavailable {manager.id} manager.")

    # Use an iterator to not trigger log messages for the 'managers' subcommand
    # which is not using this variable.
    active_managers = filter(keep_available, selected_managers)

    return active_managers
