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

The {command}`mpm` subcommands render heterogeneous tables (different columns per
command) but share the same output machinery. This module owns all of it:

- {class}`SortableField`, the vocabulary of the global `mpm --sort-by`
  selector. The selector itself is click-extra's field-vocabulary
  {class}`~click_extra.table.SortByOption`, and the per-table resolution (sort
  by the selected fields the table carries, keep the original row order when it
  carries none) happens inside {func}`click_extra.table.print_table`, from the
  field each header pairs with its column in the registries below.
- The per-command **column registries**, each pairing a click-extra
  {class}`~click_extra.table.ColumnSpec` (whose ID addresses the column from
  `--columns`) with the {class}`SortableField` the column carries (`None`
  for a column that cannot drive the sort). A registry is the single source of
  truth for its command: the same tuple feeds the `@columns_option` declaration
  (which validates the user selection) and {func}`print_projected_table`
  (which projects headers and rows before rendering).
- {func}`print_projected_table` and {func}`print_serialized_and_exit`, the
  human-friendly and machine-friendly rendering paths every table-producing
  subcommand goes through.

```{note}
The registry pairs' second element is annotated `str | None` rather than
`SortableField | None`: on Python 3.10, {class}`SortableField` extends
`backports.strenum.StrEnum`, whose stubs type the members as plain
{class}`str`, so the tighter annotation only checks under 3.11+.
`StrEnum` members being {class}`str` subclasses, the wider annotation is
accurate on every supported version.
```
"""

from __future__ import annotations

import shutil
import sys
from contextlib import contextmanager

from click_extra.context import COLUMNS, TABLE_FORMAT
from click_extra.table import (
    AUTO_WIDTH,
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
    from collections.abc import Iterable, Iterator, Sequence

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
        ColumnSpec(
            "supported",
            "Supported",
            "Support status on the current platform.",
            max_width=AUTO_WIDTH,
        ),
        None,
    ),
    (
        ColumnSpec(
            "cli",
            "CLI",
            "Location of the manager's binary on the system.",
            max_width=AUTO_WIDTH,
        ),
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
"""Columns of the `mpm managers` table.

`supported` and `cli` are the two whose content no manager bounds: the first
enumerates every platform a manager runs on when they do not collapse to a
group name, the second holds a filesystem path. Both take
{data}`~click_extra.table.AUTO_WIDTH` so they share whatever the fixed columns
leave on the terminal and wrap inside their own cell, instead of stretching the
table past the edge and mangling every border.
"""

MANAGERS_DETECTED_COLUMNS: tuple[str, ...] = (
    "manager_id",
    "manager_name",
    "cli",
    "version",
)
"""Columns kept by the default, detected-only view of the `mpm managers` table.

A detected manager is by definition supported on this platform, found and
executable, so `supported` and `executable` render the same ✓ on every row and
carry no information. Both come back in the wider views, where an unsupported
platform or a missing binary makes them vary again. Only the *default* selection
narrows: `--columns` still addresses every column of {data}`MANAGERS_COLUMNS`.
"""

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
"""Columns of the `mpm installed` table."""

OUTDATED_COLUMNS: tuple[tuple[ColumnSpec, str | None], ...] = (
    *INSTALLED_COLUMNS,
    (
        ColumnSpec(
            "latest_version", "Latest version", "Version available for upgrade."
        ),
        None,
    ),
)
"""Columns of the `mpm outdated` table."""

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
            max_width=AUTO_WIDTH,
        ),
        None,
    ),
)
"""Columns of the `mpm search` table.

The `description` column exists in the registry (so `--columns` can select it)
but stays out of the default selection unless `--description` (or `--extended`,
which searches descriptions) is passed.

It is also the only column of any registry holding free prose, of a length no
manager bounds: a single verbose match used to stretch the table far past the
terminal and wrap every row at the edge, mangling the borders.
{data}`~click_extra.table.AUTO_WIDTH` caps it at whatever the other columns
leave on the terminal, so the description wraps inside its own cell.
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
"""Columns of the `mpm which` table."""


def column_specs(
    columns: Sequence[tuple[ColumnSpec, str | None]],
) -> tuple[ColumnSpec, ...]:
    """Extract the bare {class}`~click_extra.table.ColumnSpec` tuple from a column
    registry."""
    return tuple(spec for spec, _ in columns)


@contextmanager
def _terminal_width_budget(ctx: Context) -> Iterator[None]:
    """Give a table the whole terminal, then put the help budget back.

    click-extra sizes every {data}`~click_extra.table.AUTO_WIDTH` column from
    `ctx.make_formatter().width`, the same budget that lays out help screens.
    Click caps that at 80 columns unless `max_content_width` says otherwise, which
    is right for prose and far too tight for a data table: the fixed columns alone
    can exceed it, leaving each auto column at
    {data}`~click_extra.table.MIN_COLUMN_WIDTH` however wide the terminal is, so a
    path wraps every eight characters on a 200-column screen.

    Raising the cap on the `mpm` group instead was measured and rejected. mpm's
    help text is hand-formatted against an 80-character reference, and a large
    cap stops Click wrapping altogether: `mpm --help` then emitted a 463-character
    line. So the widening is scoped to the render and undone after it, leaving
    every help screen untouched.
    """
    previous = ctx.max_content_width
    ctx.max_content_width = shutil.get_terminal_size().columns
    try:
        yield
    finally:
        ctx.max_content_width = previous


def print_projected_table(
    ctx: Context,
    columns: Sequence[tuple[ColumnSpec, str | None]],
    rows: Iterable[dict[str, str | None]],
    default_ids: Sequence[str] | None = None,
) -> None:
    """Render dict `rows` as a table projected through `--columns`.

    The `--columns` selection restricts and reorders the rendering,
    SQL-`SELECT`-style; click-extra's
    {class}`~click_extra.table.ColumnsOption` already validated it against the
    same `columns` registry, so unknown IDs never reach this point.
    `default_ids` is the selection applied when the user passed none
    (`search` uses it to hide the description column unless
    `--description`); `None` keeps every column in canonical order.

    Sorting stays on mpm's global `--sort-by`: each header pairs its label
    with the sortable field the column carries, and click-extra's
    {meth}`~click_extra.context.Context.print_table` reads the selection
    (with the `--table-format` one) from the shared context `meta` and
    resolves it per table. A sort field whose column is projected out is simply
    skipped, and a table carrying none of the selected fields keeps its
    original row order.

    ```{note}
    The width limits are forwarded by hand, from the same specs the projection
    just resolved. click-extra reads them off {class}`~click_extra.table.ColumnSpec`
    headers on its own, but mpm's headers are `(label, sortable field)` pairs
    instead: a spec's ID addresses the column for `--columns` while the field it
    sorts on may differ (`installed_version` sorts on `version`) or be absent
    altogether, which a bare spec cannot express.
    ```
    """
    selected = ctx.meta.get(COLUMNS) or tuple(default_ids or ())
    projected = select_columns(column_specs(columns), selected)
    sort_field = {spec.id: field for spec, field in columns}
    ids = tuple(spec.id for spec in projected)
    with _terminal_width_budget(ctx):
        ctx.print_table(
            [select_row(row, ids, ids) for row in rows],
            tuple((spec.label, sort_field[spec.id]) for spec in projected),
            max_column_widths=tuple(spec.max_width for spec in projected),
        )


def print_serialized_and_exit(ctx: Context, data: object) -> None:
    """Render `data` in the active serialization format, then exit.

    When the global `--table-format` resolves to one of the structured
    serialization formats (JSON, YAML, TOML, XML, ...), serialize `data` under
    the shared `mpm` root element and stop the program. Otherwise return, so
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
