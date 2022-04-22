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

"""Helpers and utilities to render and print content."""

import builtins
import json
import sys
from functools import partial
from io import StringIO
from operator import itemgetter
from pathlib import Path
from unittest.mock import patch

if sys.version_info >= (3, 8):
    from functools import cached_property
else:
    from boltons.cacheutils import cachedproperty as cached_property

from boltons.iterutils import flatten
from boltons.strutils import strip_ansi
from click_extra import echo, get_current_context, style
from click_extra.tabulate import TabularOutputFormatter
from tabulate import DataRow, TableFormat, tabulate

from . import __version__
from .bar_plugin import MPMPlugin
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
    """Utility to print a table and sort its content."""
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

    ctx = get_current_context()
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
    echo(f"{total_installed} package{plural} total{per_manager_totals}.")


class BarPluginRenderer(MPMPlugin):
    """All utilities used to render output compatible with both Xbar and SwiftBar plugin
    dialect.

    The minimal code to locate ``mpm`` and call it and print its output resides in the plugin itself.

    All other stuff, especially the layout-related code is managed here, to allow for more complex
    rendering, intricate layouts and easier updates.
    """

    @cached_property
    def submenu_layout(self):
        """Group packages into manager sub-menus.

        If ``True``, will replace the default flat layout with an alternative structure
        where actions are grouped into submenus, one for each manager.
        """
        return self.getenv_bool("VAR_SUBMENU_LAYOUT", False)

    @cached_property
    def dark_mode(self):
        """Detect dark mode by inspecting environment variables."""
        if self.is_swiftbar:
            return self.getenv_str("OS_APPEARANCE", "light") == "dark"
        return self.getenv_bool("XBARDarkMode")

    @staticmethod
    def render_cli(cmd_args, plugin_format=False):
        """Return a formatted CLI in the requested format.

        Returns a space-separated strings build on ``cmd_args`` list.

        If ``plugin_format`` is ``True`` returns a string compatible with Xbar and SwiftBar plugin format,
        i.e. this schema:

        .. code-block::

            shell=cmd_args[0] param1=cmd_args[1] param2=cmd_args[2] param2=cmd_args[2] ...
        """
        assert isinstance(cmd_args, tuple)
        # Serialize Path instances.
        cmd_args = map(str, flatten(cmd_args))

        if not plugin_format:
            return " ".join(cmd_args)

        # Renders CLI into the *bar plugin dialect.
        plugin_params = []
        for index, param_value in enumerate(cmd_args):
            param_id = "shell" if index == 0 else f"param{index}"
            plugin_params.append(f"{param_id}={param_value}")
        return " ".join(plugin_params)

    def print_cli_item(self, *args):
        """Print two CLI entries:

        - one that is silent
        - a second one that is the exact copy of the above but forces the execution
          by the way of a visible terminal
        """
        self.pp(*args, "terminal=false")
        self.pp(*args, "terminal=true", "alternate=true")

    def print_upgrade_all_item(self, manager, submenu=""):
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
    """Simple rendering format with single-space separated columns."""

    @staticmethod
    def render_table(table_data):
        """Render a table data with pre-configured alignment.

        .. code-block:: python
            >>> table_data = [
            ...     ('xmlrpc', '0.3.1', '→', '0.4'),
            ...     ('blockblock', '5.33,VHSDGataYCcV8xqv5TSZA', '→', '5.39'),
            ...     ('sed', '2', '→', '2021.0328'),
            ... ]
            >>> print(render_table(table_data))
            xmlrpc                          0.3.1 → 0.4
            blockblock 5.33,VHSDGataYCcV8xqv5TSZA → 5.39
            sed                                 2 → 2021.0328
        """
        return tabulate(
            table_data,
            tablefmt=BarPluginRenderer.plain_table_format,
            colalign=("left", "right", "center", "left"),
            disable_numparse=True,
        )

    def _render(self, outdated_data):
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
                    (p["name"], p["installed_version"], "→", p["latest_version"]),
                    p["upgrade_cli"],
                )
                for p in manager["packages"]
            ]

            # Table-like rendering
            if self.table_rendering:
                header = f"{manager['id']} - {package_count} {package_label}"
                formatted_lines = self.render_table([p[0] for p in table]).splitlines()

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

    def render(self, outdated_data):
        # Capture all print statement.
        capture = StringIO()
        print_capture = partial(print, file=capture)
        with patch.object(builtins, "print", new=print_capture):
            self._render(outdated_data)
        return capture.getvalue()

    def print(self, outdated_data):
        # Capturing the output of the plugin and re-printing it will introduce an
        # extra line returns, hence the extra rstrip() call.
        echo(self.render(outdated_data).rstrip())
