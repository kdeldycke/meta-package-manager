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

from functools import wraps
from typing import Iterator

from . import logger
from .base import Package, PackageManager

"""Utilities and helper to organize, inspect and audit the capabilities of mpm and package managers."""


def search_capabilities(extended_support: bool = True, exact_support: bool = True):
    """Decorator factory to be used on ``search()`` operations to signal ``mpm``
    framework manager's capabilities."""

    def decorator(function):
        @wraps(function)
        def wrapper(
            self: PackageManager, query: str, extended: bool, exact: bool
        ) -> Iterator[Package]:

            refilter = False

            if exact:
                if not exact_support:
                    refilter = True
                    logger.warning(
                        f"{self.id} does not implement exact search operation. Refiltering of raw results has been activated"
                    )

            if extended:
                if not extended_support:
                    refilter = True
                    logger.warning(
                        f"{self.id} does not implement extended search operation. Refiltering of raw results has been activated."
                    )

            return function(self, query, extended, exact)  # type: ignore

        return wrapper

    return decorator
