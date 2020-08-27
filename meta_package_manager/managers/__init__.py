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
        3 - are not virtual (i.e. have a non null cli_name property).

    Returns an `OrderedDict` sorted by manager's ID.
    """
    register = {}

    for py_file in Path(__file__).parent.glob("*.py"):
        logger.debug(f"Search manager definitions in {py_file}")
        module = import_module(".{}".format(py_file.stem), package=__package__)

        for _, klass in inspect.getmembers(module, inspect.isclass):
            if issubclass(klass, PackageManager) and not klass.virtual:
                logger.debug(f"Found {klass!r}")
                manager = klass()
                register[manager.id] = manager
            else:
                logger.debug(f"{klass!r} is not a valid manager definition")

    # Sort pool entries by ID.
    # TODO: propose an OrderedDrozenDict in boltons and use it here.
    return OrderedDict(sorted(register.items()))
