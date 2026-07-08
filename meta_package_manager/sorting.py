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
"""Field-aware sorting of the multi-manager result tables.

The :command:`mpm` subcommands render heterogeneous tables (different columns per
command) but share one global ``mpm --sort-by`` selector. This module owns the
vocabulary of sortable fields (:py:class:`SortableField`) and the row-sort key builder
(:py:func:`print_sorted_table`) that maps the selected fields onto whichever columns a
given table happens to carry.
"""

from __future__ import annotations

import sys
from functools import partial

from boltons.strutils import strip_ansi
from click_extra.table import print_table

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from backports.strenum import StrEnum  # type: ignore[import-not-found]

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from click_extra.table import TableFormat


class SortableField(StrEnum):
    """Fields IDs allowed to be sorted."""

    MANAGER_ID = "manager_id"
    MANAGER_NAME = "manager_name"
    PACKAGE_ID = "package_id"
    PACKAGE_NAME = "package_name"
    VERSION = "version"


def _column_row_key(order: Sequence[int], row: Sequence[str | None]) -> tuple:
    """Build a row's sort key over the ``order`` columns, stripped and casefolded.

    Empty or ``None`` cells collate as the empty string. Mirrors the per-cell
    comparison click-extra's own table sorter applies.
    """
    return tuple(strip_ansi(cell).casefold() if (cell := row[i]) else "" for i in order)


def _sort_column_order(
    fields: Sequence[SortableField | None],
    sort_by: Sequence[SortableField],
) -> tuple[int, ...] | None:
    """Resolve ``sort_by`` fields to a column-index order for a table's ``fields``.

    Returns the order in which columns drive the row sort: the requested fields the
    table carries come first, in ``sort_by`` priority order and de-duplicated, then
    the remaining columns provide natural left-to-right tie-breaking. Returns
    ``None`` when the table carries none of the requested fields, signalling that
    rows should keep their original order.
    """
    primaries = [fields.index(f) for f in dict.fromkeys(sort_by) if f in fields]
    if not primaries:
        return None
    return (*primaries, *(i for i in range(len(fields)) if i not in primaries))


def print_sorted_table(
    headers: Sequence[tuple[str, SortableField | None]],
    table: Sequence[Sequence[str | None]],
    sort_by: Sequence[SortableField],
    *,
    table_format: TableFormat | None = None,
) -> None:
    """Render ``table`` with click-extra, sorting rows by the ``sort_by`` columns.

    Each ``headers`` entry pairs a column label with the :class:`SortableField` it
    carries, or ``None`` for a column that cannot be sorted on. ``sort_by`` lists the
    fields to order by, in priority order: rows sort by the first field this table
    carries, then each subsequent field as a tie-breaker, with any remaining columns
    breaking further ties in their natural left-to-right order. Fields the table does
    not carry are skipped; a ``sort_by`` matching no column leaves the rows in their
    original order.

    Reimplements the ``print_sorted_table`` helper click-extra dropped in ``8.0.0``,
    where :class:`click_extra.table.SortByOption` instead bakes the sort key into
    ``ctx.print_table``. That option derives its choices from a single command's
    columns, whereas mpm shares one global ``mpm --sort-by`` across subcommands
    with heterogeneous tables, so the key is built here.
    """
    fields = [field for _, field in headers]
    order = _sort_column_order(fields, sort_by)
    sort_key: Callable[[Sequence[str | None]], tuple] | None = (
        partial(_column_row_key, order) if order is not None else None
    )
    print_table(
        table,
        [label for label, _ in headers],
        table_format=table_format,
        sort_key=sort_key,
    )
