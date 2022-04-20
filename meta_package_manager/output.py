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
import io
import json
from functools import partial
from operator import itemgetter
from pathlib import Path
from unittest.mock import patch

from boltons.iterutils import flatten
from boltons.strutils import strip_ansi
from click_extra import echo, get_current_context, style
from click_extra.tabulate import TabularOutputFormatter

from . import __version__, bar_plugin
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
    """All utilities used to render output compatible with both Xbar and SwiftBar plugin dialect.

    The minimal code to locate ``mpm`` and call it and print its output resides in the plugin itself.

    All other stuff, especially the layout-related code is managed here, to allow for more complex
    rendering, intricate layouts and easier updates.
    """

    PLUGIN_DIALECTS = frozenset({"xbar", "swiftbar"})
    """List of supported plugin rendering formats."""

    def __init__(self, dialect="swiftbar", submenu_layout=False, table_rendering=True):
        assert dialect in self.PLUGIN_DIALECTS
        self.dialect = dialect
        self.submenu_layout = submenu_layout
        self.table_rendering = table_rendering

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

        * one that is silent
        * a second one that is the exact copy of the above but forces the execution
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
                bar_plugin.FONTS["normal"],
                "refresh=true",
            )

    def _render(self, outdated_data):
        managers = outdated_data.values()

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

        # String used to separate the left and right columns.
        col_sep = "  " if self.table_rendering else " "
        up_sep = " → "

        # Compute global length constant.
        global_outdated_len = max(len(str(len(m["packages"]))) for m in managers)
        package_str = "package"
        right_col_len = global_outdated_len + len(package_str) + 1  # +1 for plural

        # Global maximum length of labels.
        global_len_name = max(len(p["name"]) for m in managers for p in m["packages"])
        global_len_manager = max(len(m["id"]) for m in managers)
        global_len_left = max((global_len_manager, global_len_name))
        global_len_installed = max(
            len(p["installed_version"]) for m in managers for p in m["packages"]
        )
        global_len_latest = max(
            len(p["latest_version"]) for m in managers for p in m["packages"]
        )
        global_len_right = max(
            [
                right_col_len,
                global_len_installed + len(up_sep) + global_len_latest,
            ]
        )

        for manager in managers:
            plural = "s" if len(manager["packages"]) > 1 else ""
            package_label = f"{package_str}{plural}"

            name_max_len = installed_max_len = latest_max_len = 0

            if self.table_rendering:

                if self.submenu_layout:
                    # Re-define layout maximum dimensions for each manager.
                    left_col_len = global_len_manager
                    if manager["packages"]:
                        name_max_len = max(len(p["name"]) for p in manager["packages"])
                        installed_max_len = max(
                            len(p["installed_version"]) for p in manager["packages"]
                        )
                        latest_max_len = max(
                            len(p["latest_version"]) for p in manager["packages"]
                        )

                else:
                    # Layout constraints are defined across all managers.
                    left_col_len = name_max_len = global_len_left
                    installed_max_len = global_len_installed
                    latest_max_len = global_len_latest
                    right_col_len = global_len_right

                outdated_label = (
                    f"{len(manager['packages']):>{global_outdated_len}} {package_label:<8}"
                )

                header = f"{manager['id']:<{left_col_len}}{col_sep}{outdated_label:>{right_col_len}}"

            # Variable-width / non-table / non-monospaced rendering.
            else:
                header = (
                    f"{len(manager['packages'])} outdated {manager['name']} {package_label}"
                )

            # Print section separator before printing the manager header.
            print("---")

            # Print section header.
            error = ""
            if self.submenu_layout and manager.get("errors", None):
                error = "⚠️ "
            self.pp(f"{error}{header}", bar_plugin.FONTS["summary"])

            # Print a menu entry for each outdated packages.
            for pkg_info in manager["packages"]:
                self.print_cli_item(
                    f"{submenu}{pkg_info['name']:<{name_max_len}}"
                    + col_sep
                    + f"{pkg_info['installed_version']:>{installed_max_len}}"
                    + up_sep
                    + f"{pkg_info['latest_version']:<{latest_max_len}}",
                    pkg_info["upgrade_cli"],
                    bar_plugin.FONTS["package"],
                    "refresh=true",
                )

            self.print_upgrade_all_item(manager, submenu)

            for error_msg in manager.get("errors", []):
                print("-----" if self.submenu_layout else "---")
                self.print_error(error_msg, submenu)

    def render(self, outdated_data):
        # Capture all print statement.
        capture = io.StringIO()
        print_capture = partial(print, file=capture)
        with patch.object(builtins, "print", new=print_capture):
            self._render(outdated_data)
        return capture.getvalue()

    def print(self, outdated_data):
        # Capturing the output of the plugin and re-printing it will introduce an extra line returns, hence the extra rstrip() call.
        echo(self.render(outdated_data).rstrip())
