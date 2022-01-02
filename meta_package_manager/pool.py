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

""" Registration, indexing and caching of package manager definitions. """

import inspect
from importlib import import_module
from pathlib import Path

from boltons.cacheutils import LRI, cached
from boltons.iterutils import unique
from click_extra.logging import logger

from .base import PackageManager

MANAGER_SUBFOLDER = "managers"
"""Relative subfolder where to search for manager definition files."""


# Cache the global pool of registered manager definitions to speed-up lookups.
@cached(LRI(max_size=1))
def pool():
    """Search for package manager definitions locally and store them into an
    internal register.

    Is considered valid package manager, definitions classes which:
        1 - are located in the `managers` subfolder, and
        2 - are sub-classes of PackageManager, and
        3 - are not virtual (i.e. have a non null `cli_names` property).
    """
    register = {}

    for py_file in Path(__file__).parent.joinpath(MANAGER_SUBFOLDER).glob("*.py"):
        logger.debug(f"Search manager definitions in {py_file}")
        module = import_module(
            f".{MANAGER_SUBFOLDER}.{py_file.stem}", package=__package__
        )

        for _, klass in inspect.getmembers(module, inspect.isclass):
            if issubclass(klass, PackageManager) and not klass.virtual:
                logger.debug(f"Found {klass!r}")
                manager = klass()
                register[manager.id] = manager
            else:
                logger.debug(f"{klass!r} is not a valid manager definition")

    return register


# Pre-compute all sorts of constants.

ALL_MANAGER_IDS = tuple(sorted(pool()))
""" All recognized manager IDs.

Is a list of sorted items to provide consistency across all UI, and reproducability in
the order package managers are evaluated.
"""

DEFAULT_MANAGER_IDS = tuple(mid for mid in ALL_MANAGER_IDS if pool()[mid].supported)
""" All manager IDs supported on the current platform.

Must keep the same order defined by ALL_MANAGER_IDS.
"""

UNSUPPORTED_MANAGER_IDS = tuple(
    mid for mid in ALL_MANAGER_IDS if mid not in DEFAULT_MANAGER_IDS
)
""" All manager IDs unsupported on the current platform.

Order is not important here as this list will be used to discard managers from selection
sets.
"""


ALLOWED_EXTRA_OPTION = frozenset({"ignore_auto_updates", "stop_on_error", "dry_run"})
"""List of extra options that are allowed to be set on managers during the use of the
:py:func:`meta_package_manager.managers.select_managers` helper below."""


def select_managers(
    keep=None,
    drop=None,
    drop_unsupported=True,
    drop_inactive=True,
    **extra_options,
):
    """Utility method to extract a subset of the manager pool based on selection list
    (`keep` parameter) and exclusion list (`drop` parameter) criterion.

    By default, all managers supported on the current platform are selected. Unless
    `drop_unsupported` is set to False, in which case all managers implemented by mpm
    are selected, regardless of their supported platform.

    `drop_inactive` filters out managers that where not found on the system.

    Finally, `extra_options` parameters are fed to the manager objects from the pool to
    set some options.

    Returns a generator producing a manager object one after the other.
    """
    if not keep:
        keep = DEFAULT_MANAGER_IDS if drop_unsupported else ALL_MANAGER_IDS
    if not drop:
        drop = set()
    assert set(ALL_MANAGER_IDS).issuperset(keep)
    assert set(ALL_MANAGER_IDS).issuperset(drop)

    assert ALLOWED_EXTRA_OPTION.issuperset(extra_options)

    # Only keeps the subset selected by the user.
    selected_ids = keep

    # Deduplicate managers IDs while preserving order, then remove excluded managers.
    for manager_id in (mid for mid in unique(selected_ids) if mid not in drop):
        manager = pool()[manager_id]

        # Filters out inactive managers.
        if drop_inactive and not manager.available:
            logger.warning(f"Skip unavailable {manager_id} manager.")
            continue

        # Apply manager-level options.
        for param, value in extra_options.items():
            assert hasattr(manager, param)
            setattr(manager, param, value)

        yield manager
