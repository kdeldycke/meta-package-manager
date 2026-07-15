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
"""Vocabulary of the fields the global ``mpm --sort-by`` can order tables by.

The :command:`mpm` subcommands render heterogeneous tables (different columns
per command) but share one global ``mpm --sort-by`` selector. This module only
owns the vocabulary of sortable fields (:py:class:`SortableField`): the
selector itself is click-extra's field-vocabulary
:py:class:`~click_extra.table.SortByOption`, and the per-table resolution
(sort by the selected fields the table carries, keep the original row order
when it carries none) happens inside
:py:func:`click_extra.table.print_table`, from the field each header pairs
with its column in ``cli.py``'s column registries.
"""

from __future__ import annotations

import sys

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from backports.strenum import StrEnum  # type: ignore[import-not-found]


class SortableField(StrEnum):
    """Fields IDs allowed to be sorted."""

    MANAGER_ID = "manager_id"
    MANAGER_NAME = "manager_name"
    PACKAGE_ID = "package_id"
    PACKAGE_NAME = "package_name"
    VERSION = "version"
