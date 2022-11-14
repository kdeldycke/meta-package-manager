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

"""Helpers and utilities to render and print content.

.. todo::

    Some of these are good candidates for upstream contribution to ``click.extra``.
"""

from __future__ import annotations

import builtins
import json
import sys
from collections import Counter
from functools import partial
from io import StringIO
from operator import itemgetter
from pathlib import Path
from typing import Any, Sequence
from unittest.mock import patch

if sys.version_info >= (3, 8):
    from functools import cached_property
else:
    from boltons.cacheutils import cachedproperty as cached_property

from boltons.iterutils import flatten
from boltons.strutils import strip_ansi
from click_extra import echo, get_current_context, style
from click_extra.colorize import default_theme as theme
from click_extra.tabulate import output_formats
from tabulate import DataRow, TableFormat, tabulate

from . import logger
from .bar_plugin import MPMPlugin  # type: ignore
from .pool import pool
from .version import TokenizedString

SORTABLE_FIELDS = {
    "manager_id",
    "manager_name",
    "package_id",
    "package_name",
    "version",
}
"""List of fields IDs allowed to be sorted."""


def colored_diff(a, b, style_common=None, style_a=None, style_b=None):
    """Highlight the most common left part between ``a`` and ``b`` strings and their
    trailing differences.

    Always returns 2 strings.
    """
    # Set defaults stling methods.
    style_common = partial(style, fg="bright_black")
    style_a = partial(style, fg="red")
    style_b = partial(style, fg="green")

    if isinstance(a, TokenizedString):
        a = str(a)
    if isinstance(b, TokenizedString):
        b = str(b)

    common_size = 0
    if a and b:
        while (min(len(a), len(b)) - 1) >= common_size and a[common_size] == b[
            common_size
        ]:
            common_size += 1

    # Styling of common and different parts.
    colored_a = ""
    colored_b = ""
    if common_size:
        colored_a = colored_b = style_common(a[:common_size])
    if a:
        colored_a += style_a(a[common_size:])
    if b:
        colored_b += style_b(b[common_size:])

    return colored_a, colored_b


output_formats = sorted(output_formats + ["json"])


def print_json(data):
    """Pretty-print Python data to JSON and output results to ``<stdout>``.

    Serialize :py:class:`pathlib.Path` and :py:class:`meta_package_manager.version.TokenizedString` objects.
    """

    def serialize_objects(obj):
        if isinstance(obj, (TokenizedString, Path)):
            return str(obj)
        raise TypeError(repr(obj) + " is not JSON serializable.")

    echo(
        json.dumps(
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
    """Print a sorted table.

    ``header_defs`` parameter is an ordered list of tuple whose first item is the column's label and the second the column's ID. Example:

    .. code-block:: python

        [("Column 1", "column1"), ("User's name", "name"), ("Package manager", "manager_id"), ...]

    Rows can be sorted by providing the column's ID to ``sort_key`` parameter. By default, ``None`` means the table will be sorted
    in the order of columns provided by ``header_defs``.
    """
    # Do not print anything, not even table headers if no rows.
    if not rows:
        return

    header_labels = (style(label, bold=True) for label, _ in header_defs)

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
        2. Strip terminal color formatting;
        3. Then tokenize each cell's content for user-friendly natural sorting.
        """
        sorting_key = []
        for cell in itemgetter(*sort_order)(line):
            if isinstance(cell, TokenizedString):
                key = cell
            elif not cell:
                key = None
            else:
                key = TokenizedString(strip_ansi(cell))
            sorting_key.append(key)
        return tuple(sorting_key)

    ctx = get_current_context()
    ctx.find_root().print_table(sorted(rows, key=sort_method), header_labels)


def print_stats(manager_stats: Counter) -> None:
    """Prints statistics to ``<stderr>``: total packages and a break down by package
    manager.

    Prints something like:

    .. code-block:: text

        16 packages total (brew: 2, pip: 2, gem: 2, cask: 2, mas: 2, vscode: 2, npm: 2, composer: 0).
    """
    per_manager_totals = ""
    if manager_stats:
        per_manager_totals = (
            f" ({', '.join(f'{k}: {v}' for k, v in manager_stats.most_common())})"
        )
    if sys.version_info >= (3, 10):
        total = manager_stats.total()
    else:
        total = sum(manager_stats.values())
    plural = "s" if total > 1 else ""
    echo(f"{total} package{plural} total{per_manager_totals}.", err=True)


class BarPluginRenderer(MPMPlugin):
    """All utilities used to render output compatible with both Xbar and SwiftBar plugin
    dialect.

    The minimal code to locate ``mpm``, then call it and print its output resides in the plugin itself at
    :py:meth:`meta_package_manager.bar_plugin.MPMPlugin.mpm_exec`.

    All other stuff, especially the rendering code, is managed here, to allow for more complex
    layouts relying on external Python dependencies. This also limits the number of required updates on the
    plugin itself.
    """

    @cached_property
    def submenu_layout(self) -> bool:
        """Group packages into manager sub-menus.

        If ``True``, will replace the default flat layout with an alternative structure
        where actions are grouped into submenus, one for each manager.

        Value is sourced from the ``VAR_SUBMENU_LAYOUT`` environment variable.
        """
        return self.getenv_bool("VAR_SUBMENU_LAYOUT", False)  # type: ignore

    @cached_property
    def dark_mode(self) -> bool:
        """Detect dark mode by inspecting environment variables.

        Value is sourced from two environment variables depending on the plugin:

        - ``OS_APPEARANCE`` for SwiftBar
        - ``XBARDarkMode`` for XBar
        """
        if self.is_swiftbar:
            return self.getenv_str("OS_APPEARANCE", "light") == "dark"  # type: ignore
        return self.getenv_bool("XBARDarkMode")  # type: ignore

    @staticmethod
    def render_cli(cmd_args: tuple[str | Path, ...]) -> str:
        """Return a formatted CLI compatible with Xbar and SwiftBar plugin format.

        I.e. a string with this schema:

        .. code-block::

            shell=cmd_args[0] param1=cmd_args[1] param2=cmd_args[2] param2=cmd_args[2] ...
        """
        plugin_params = []
        # Serialize Path into string.
        for index, param_value in enumerate(map(str, flatten(cmd_args))):
            param_id = "shell" if index == 0 else f"param{index}"
            plugin_params.append(f"{param_id}={param_value}")
        return " ".join(plugin_params)

    def print_cli_item(self, *args) -> None:
        """Print two CLI entries:

        - one that is silent
        - a second one that is the exact copy of the above but forces the execution
          by the way of a visible terminal
        """
        self.pp(*args, "terminal=false")
        self.pp(*args, "terminal=true", "alternate=true")

    def print_upgrade_all_item(self, manager: dict, submenu: str = "") -> None:
        """Print the menu entry to upgrade all outdated package of a manager."""
        if manager.get("upgrade_all_cli"):
            if self.submenu_layout:
                print("-----")
            self.print_cli_item(
                f"{submenu}🆙 Upgrade all {manager['id']} packages",
                manager["upgrade_all_cli"],
                self.default_font,
                "refresh=true",
            )

    plain_table_format = TableFormat(
        lineabove=None,
        linebelowheader=None,
        linebetweenrows=None,
        linebelow=None,
        headerrow=DataRow("", " ", ""),
        datarow=DataRow("", " ", ""),
        padding=0,
        with_header_hide=None,
    )
    """Simple rendering format with single-space separated columns used in the function below."""

    @staticmethod
    def render_table(
        table_data: Sequence[Sequence[str]] | None,
    ) -> Any | list:
        """Renders a table data with pre-configured alignment centered around the third
        column.

        Returns a list of strings, one item per line.

        .. code-block:: pycon

            >>> table_data = [
            ...     ('xmlrpc', '0.3.1', '→', '0.4'),
            ...     ('blockblock', '5.33,VHSDGataYCcV8xqv5TSZA', '→', '5.39'),
            ...     ('sed', '2', '→', '2021.0328'),
            ... ]
            >>> print(render_table(table_data))
            xmlrpc                          0.3.1 → 0.4
            blockblock 5.33,VHSDGataYCcV8xqv5TSZA → 5.39
            sed                                 2 → 2021.0328

        ..todo::

            Use upcoming ``tabulate.SEPARATING_LINE`` to produce the whole bar plugin table in one go
            and have all version numbers from all managers aligned. See:
            https://github.com/astanin/python-tabulate/commit/dab256d1f64da97720c1459478a3cc0a4ea7a91e
        """
        if not table_data:
            return []
        return tabulate(
            table_data,
            tablefmt=BarPluginRenderer.plain_table_format,
            colalign=("left", "right", "center", "left"),
            disable_numparse=True,
        ).splitlines()

    def _render(self, outdated_data) -> None:
        """Main method implementing the final structured rendering in *Bar plugin
        dialect.

        ..todo::

            Wait for ANSI-aware layout in table to be merged upstream so we can highly version
            differences in bar plugin. See: https://github.com/astanin/python-tabulate/pull/184
        """
        managers = outdated_data.values()
        font = self.monospace_font if self.table_rendering else self.default_font

        # Print menu bar icon with number of available upgrades.
        total_outdated = sum(len(m["packages"]) for m in managers)
        total_errors = sum(len(m.get("errors", [])) for m in managers)
        self.pp(
            (f"🎁↑{total_outdated}" if total_outdated else "📦✓")
            + (f" ⚠️{total_errors}" if total_errors else ""),
            "dropdown=false",
        )

        # Prefix for section content.
        submenu = "--" if self.submenu_layout else ""

        for manager in managers:
            package_count = len(manager["packages"])
            plural = "s" if package_count > 1 else ""
            package_label = f"package{plural}"

            table = [
                (
                    (
                        p.get("name") or p.get("id"),
                        p["installed_version"],
                        "→",
                        p["latest_version"],
                    ),
                    p["upgrade_cli"],
                )
                for p in manager["packages"]
            ]

            # Table-like rendering
            if self.table_rendering:
                header = f"{manager['id']} - {package_count} {package_label}"
                formatted_lines = self.render_table([p[0] for p in table])

            # Variable-width / non-table / non-monospaced rendering.
            else:
                header = f"{package_count} outdated {manager['name']} {package_label}"
                formatted_lines = [" ".join(map(str, p[0])) for p in table]

            upgrade_cli_list = [p[1] for p in table]

            assert len(formatted_lines) == len(upgrade_cli_list)

            # Print section separator before printing the manager header.
            print("---")

            # Print section header.
            error = ""
            if self.submenu_layout and manager.get("errors", None):
                error = "⚠️ "
            self.pp(f"{error}{header}", font)

            # Print a menu entry for each outdated packages.
            for line, upgrade_cli in zip(formatted_lines, upgrade_cli_list):
                self.print_cli_item(
                    f"{submenu}{line}", upgrade_cli, font, "refresh=true"
                )

            self.print_upgrade_all_item(manager, submenu)

            for error_msg in manager.get("errors", []):
                print("-----" if self.submenu_layout else "---")
                self.print_error(error_msg, submenu)

    def render(self, outdated_data) -> str:
        """Wraps the :py:meth:`meta_package_manager.output.BarPluginRenderer._render`
        function above to capture all ``print`` statements."""
        capture = StringIO()
        print_capture = partial(print, file=capture)
        with patch.object(builtins, "print", new=print_capture):
            self._render(outdated_data)
        return capture.getvalue()

    def add_upgrade_cli(self, outdated_data):
        """Augment the outdated data from ``mpm outdated`` subcommand with upgrade CLI
        fields for bar plugin consumption."""
        for manager_id, manager_data in outdated_data.items():
            if manager_data.get("packages"):
                manager = pool.get(manager_id)

                # Produce the full-upgrade CLI.
                try:
                    upgrade_all_cli = manager.upgrade_all_cli()
                except NotImplementedError:
                    # Fallback on mpm itself which is capable of simulating a full
                    # upgrade.
                    logger.warning(
                        f"{theme.invoked_command(manager_id)} does not implement upgrade_all_cli."
                    )
                    upgrade_all_cli = (
                        *self.mpm_exec,
                        f"--{manager_id}",
                        "upgrade",
                        "--all",
                    )
                    logger.debug(f"Fallback to direct mpm call: {upgrade_all_cli}")

                # Update outdated data with the full-upgrade CLI.
                outdated_data[manager_id]["upgrade_all_cli"] = self.render_cli(
                    upgrade_all_cli
                )

                # Add for each package its upgrade CLI.
                for package in manager_data["packages"]:
                    # Generate the version-less upgrade CLI to be used by the *bar
                    # plugin.
                    upgrade_cli = None
                    try:
                        upgrade_cli = self.render_cli(
                            manager.upgrade_one_cli(package["id"])
                        )
                    except NotImplementedError:
                        pass
                    package["upgrade_cli"] = upgrade_cli

        return outdated_data

    def print(self, outdated_data) -> None:
        """Print the final plugin rendering to ``<stdout>``.

        Capturing the output of the plugin and re-printing it will introduce an extra
        line return, hence the extra call to ``rstrip()``.
        """
        outdated_data = self.add_upgrade_cli(outdated_data)
        echo(self.render(outdated_data).rstrip())
