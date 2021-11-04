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

""" Helpers and utilities to render and print content. """

from operator import itemgetter
from pathlib import Path

import click
from boltons.strutils import strip_ansi
from click_extra.tabulate import TabularOutputFormatter
from simplejson import dumps as json_dumps

from . import __version__
from .version import TokenizedString

# List of fields IDs allowed to be sorted.
SORTABLE_FIELDS = {
    "manager_id",
    "manager_name",
    "package_id",
    "package_name",
    "version",
}


def not_implemented_json(data, headers, **kwargs):
    raise NotImplementedError(
        "JSON rendering is not generic and need specific subcommand implementation."
    )


# Add our custom JSON format to the output formatter. Link it to a dummy renderer
# as we plan to intercept the JSON settings in each subcommand.
TabularOutputFormatter.register_new_formatter("json", not_implemented_json)


def print_json(data):
    """Utility function to print data structures into pretty printed JSON.

    Also care of internal objects like `TokenizedString` and `Path`.
    """

    def serialize_objects(obj):
        if isinstance(obj, (TokenizedString, Path)):
            return str(obj)
        raise TypeError(repr(obj) + " is not JSON serializable.")

    click.echo(
        json_dumps(
            data,
            sort_keys=True,
            indent=4,
            separators=(",", ": "),
            default=serialize_objects,
        ),
        # Do not pollute output with ANSI codes.
        color=False,
    )


def print_table(header_defs, rows, sort_key=None):
    """Utility to print a table and sort its content."""
    # Do not print anything, not even table headers if no rows.
    if not rows:
        return

    header_labels = (click.style(label, bold=True) for label, _ in header_defs)

    # Check there is no duplicate column IDs.
    header_ids = [col_id for _, col_id in header_defs if col_id]
    assert len(header_ids) == len(set(header_ids))

    # Default sorting follows the order of headers.
    sort_order = list(range(len(header_defs)))

    # Move the sorting key's index in the front of priority.
    if sort_key and sort_key in header_ids:
        # Build an index of column id's position.
        col_index = {col_id: i for i, (_, col_id) in enumerate(header_defs) if col_id}
        sort_column_index = col_index[sort_key]
        sort_order.remove(sort_column_index)
        sort_order.insert(0, sort_column_index)

    def sort_method(line):
        """Serialize line's content for natural sorting.

        1. Extract each cell value in the order provided by `sort_order`;
        2. Strip terminal color formating;
        3. Then tokenize each cell's content for user-friendly natural sorting.
        """
        sorting_key = []
        for cell in itemgetter(*sort_order)(line):
            if isinstance(cell, TokenizedString):
                key = cell
            else:
                key = TokenizedString(strip_ansi(cell))
            sorting_key.append(key)
        return tuple(sorting_key)

    ctx = click.get_current_context()
    ctx.find_root().print_table(
        sorted(rows, key=sort_method), header_labels, disable_numparse=True
    )


def print_stats(data):
    """Print statistics."""
    manager_stats = {infos["id"]: len(infos["packages"]) for infos in data.values()}
    total_installed = sum(manager_stats.values())
    per_manager_totals = ", ".join(
        (
            f"{k}: {v}"
            for k, v in sorted(manager_stats.items(), key=itemgetter(1), reverse=True)
        )
    )
    if per_manager_totals:
        per_manager_totals = f" ({per_manager_totals})"
    plural = "s" if total_installed > 1 else ""
    click.echo(f"{total_installed} package{plural} total{per_manager_totals}.")
