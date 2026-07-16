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
"""Table-output vocabulary and rendering plumbing shared by the subcommands.

The :command:`mpm` subcommands render heterogeneous tables (different columns per
command) but share the same output machinery. This module owns all of it:

- :py:class:`SortableField`, the vocabulary of the global ``mpm --sort-by``
  selector. The selector itself is click-extra's field-vocabulary
  :py:class:`~click_extra.table.SortByOption`, and the per-table resolution (sort
  by the selected fields the table carries, keep the original row order when it
  carries none) happens inside :py:func:`click_extra.table.print_table`, from the
  field each header pairs with its column in the registries below.
- The per-command **column registries**, each pairing a click-extra
  :py:class:`~click_extra.table.ColumnSpec` (whose ID addresses the column from
  ``--columns``) with the :py:class:`SortableField` the column carries (``None``
  for a column that cannot drive the sort). A registry is the single source of
  truth for its command: the same tuple feeds the ``@columns_option`` declaration
  (which validates the user selection) and :py:func:`print_projected_table`
  (which projects headers and rows before rendering).
- :py:func:`print_projected_table` and :py:func:`print_serialized_and_exit`, the
  human-friendly and machine-friendly rendering paths every table-producing
  subcommand goes through.

.. note::
    The registry pairs' second element is annotated ``str | None`` rather than
    ``SortableField | None``: on Python 3.10, :py:class:`SortableField` extends
    ``backports.strenum.StrEnum``, whose stubs type the members as plain
    :py:class:`str`, so the tighter annotation only checks under 3.11+.
    ``StrEnum`` members being :py:class:`str` subclasses, the wider annotation is
    accurate on every supported version.
"""

from __future__ import annotations

import sys

from click_extra.context import COLUMNS, TABLE_FORMAT
from click_extra.table import (
    SERIALIZATION_FORMATS,
    ColumnSpec,
    print_data,
    select_columns,
    select_row,
)

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from backports.strenum import StrEnum  # type: ignore[import-not-found]

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from click_extra import Context


class SortableField(StrEnum):
    """Fields IDs allowed to be sorted."""

    MANAGER_ID = "manager_id"
    MANAGER_NAME = "manager_name"
    PACKAGE_ID = "package_id"
    PACKAGE_NAME = "package_name"
    VERSION = "version"


MANAGERS_COLUMNS: tuple[tuple[ColumnSpec, str | None], ...] = (
    (
        ColumnSpec("manager_id", "Manager ID", "Manager's identifier."),
        SortableField.MANAGER_ID,
    ),
    (
        ColumnSpec("manager_name", "Name", "Manager's common name."),
        SortableField.MANAGER_NAME,
    ),
    (
        ColumnSpec("supported", "Supported", "Support status on the current platform."),
        None,
    ),
    (
        ColumnSpec("cli", "CLI", "Location of the manager's binary on the system."),
        None,
    ),
    (
        ColumnSpec("executable", "Executable", "Whether the binary is executable."),
        None,
    ),
    (
        ColumnSpec(
            "version",
            "Version",
            "Manager's self-reported version, and the unsatisfied requirement "
            "when stale.",
        ),
        SortableField.VERSION,
    ),
)
"""Columns of the ``mpm managers`` table."""

INSTALLED_COLUMNS: tuple[tuple[ColumnSpec, str | None], ...] = (
    (
        ColumnSpec("package_id", "Package ID", "Package's identifier."),
        SortableField.PACKAGE_ID,
    ),
    (
        ColumnSpec("package_name", "Name", "Package's common name."),
        SortableField.PACKAGE_NAME,
    ),
    (
        ColumnSpec("manager_id", "Manager", "Manager reporting the package."),
        SortableField.MANAGER_ID,
    ),
    (
        ColumnSpec(
            "installed_version", "Installed version", "Version currently installed."
        ),
        SortableField.VERSION,
    ),
)
"""Columns of the ``mpm installed`` table."""

OUTDATED_COLUMNS: tuple[tuple[ColumnSpec, str | None], ...] = (
    *INSTALLED_COLUMNS,
    (
        ColumnSpec(
            "latest_version", "Latest version", "Version available for upgrade."
        ),
        None,
    ),
)
"""Columns of the ``mpm outdated`` table."""

SEARCH_COLUMNS: tuple[tuple[ColumnSpec, str | None], ...] = (
    (
        ColumnSpec("package_id", "Package ID", "Package's identifier."),
        SortableField.PACKAGE_ID,
    ),
    (
        ColumnSpec("package_name", "Name", "Package's common name."),
        SortableField.PACKAGE_NAME,
    ),
    (
        ColumnSpec("manager_id", "Manager", "Manager reporting the match."),
        SortableField.MANAGER_ID,
    ),
    (
        ColumnSpec("latest_version", "Latest version", "Latest version available."),
        SortableField.VERSION,
    ),
    (
        ColumnSpec(
            "description",
            "Description",
            "Package description, for managers that provide one. Out of the "
            "default selection: select it explicitly or pass --description.",
        ),
        None,
    ),
)
"""Columns of the ``mpm search`` table.

The ``description`` column exists in the registry (so ``--columns`` can select it)
but stays out of the default selection unless ``--description`` (or ``--extended``,
which searches descriptions) is passed.
"""

WHICH_COLUMNS: tuple[tuple[ColumnSpec, str | None], ...] = (
    (
        ColumnSpec(
            "manager_id", "Manager ID", "Manager whose search path found the binary."
        ),
        SortableField.MANAGER_ID,
    ),
    (
        ColumnSpec(
            "priority", "Priority", "Rank of the match in the manager's search path."
        ),
        None,
    ),
    (
        ColumnSpec("cli_path", "CLI path", "Location of the matched binary."),
        None,
    ),
    (
        ColumnSpec(
            "symlink",
            "Symlink destination",
            "Resolved target when the match is a symlink.",
        ),
        None,
    ),
)
"""Columns of the ``mpm which`` table."""


def column_specs(
    columns: Sequence[tuple[ColumnSpec, str | None]],
) -> tuple[ColumnSpec, ...]:
    """Extract the bare :class:`~click_extra.table.ColumnSpec` tuple from a column
    registry."""
    return tuple(spec for spec, _ in columns)


def print_projected_table(
    ctx: Context,
    columns: Sequence[tuple[ColumnSpec, str | None]],
    rows: Iterable[dict[str, str | None]],
    default_ids: Sequence[str] | None = None,
) -> None:
    """Render dict ``rows`` as a table projected through ``--columns``.

    The ``--columns`` selection restricts and reorders the rendering,
    SQL-``SELECT``-style; click-extra's
    :class:`~click_extra.table.ColumnsOption` already validated it against the
    same ``columns`` registry, so unknown IDs never reach this point.
    ``default_ids`` is the selection applied when the user passed none
    (``search`` uses it to hide the description column unless
    ``--description``); ``None`` keeps every column in canonical order.

    Sorting stays on mpm's global ``--sort-by``: each header pairs its label
    with the sortable field the column carries, and click-extra's
    :py:func:`~click_extra.table.print_table` resolves the selection per
    table. A sort field whose column is projected out is simply skipped, and a
    table carrying none of the selected fields keeps its original row order.
    """
    selected = ctx.meta.get(COLUMNS) or tuple(default_ids or ())
    projected = select_columns(column_specs(columns), selected)
    sort_field = {spec.id: field for spec, field in columns}
    ids = tuple(spec.id for spec in projected)
    # print_table renders through the table format resolved at group setup: a
    # dynamic attribute mypy cannot see.
    ctx.find_root().print_table(  # type: ignore[attr-defined]
        [select_row(row, ids, ids) for row in rows],
        tuple((spec.label, sort_field[spec.id]) for spec in projected),
    )


def print_serialized_and_exit(ctx: Context, data: object) -> None:
    """Render ``data`` in the active serialization format, then exit.

    When the global ``--table-format`` resolves to one of the structured
    serialization formats (JSON, YAML, TOML, XML, ...), serialize ``data`` under
    the shared ``mpm`` root element and stop the program. Otherwise return, so
    the caller falls through to its human-friendly table rendering.
    """
    table_format = ctx.meta[TABLE_FORMAT]
    if table_format in SERIALIZATION_FORMATS:
        # A --columns selection does not apply here: serialized documents carry
        # the full structured payload. No "ignoring option" note is logged
        # either, since the mpm group body silences all logging for
        # serialization formats (unless at DEBUG) to keep the streams clean.
        print_data(
            data, table_format, root_element="mpm", package="meta-package-manager"
        )
        ctx.exit()
