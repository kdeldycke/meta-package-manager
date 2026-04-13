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
"""Helpers and utilities to render and print content."""

from __future__ import annotations

import builtins
import contextlib
import logging
import sys
from functools import cached_property, partial
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from boltons.iterutils import flatten
from click_extra import echo
from click_extra.colorize import default_theme as theme
from click_extra.table import TableFormat, render_table

from .bar_plugin import MPMPlugin
from .pool import pool

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from backports.strenum import StrEnum  # type: ignore[import-not-found]

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections import Counter


class SortableField(StrEnum):
    """Fields IDs allowed to be sorted."""

    MANAGER_ID = "manager_id"
    MANAGER_NAME = "manager_name"
    PACKAGE_ID = "package_id"
    PACKAGE_NAME = "package_name"
    VERSION = "version"


def print_stats(manager_stats: Counter) -> None:
    """Prints statistics to ``<stderr>``: total packages and a break down by package
    manager.

    Prints something like:

    .. code-block:: text

        10 packages total (brew: 2, pip: 2, gem: 2, vscode: 2, npm: 2, composer: 0).
    """
    per_manager_totals = ""
    if manager_stats:
        per_manager_totals = (
            f" ({', '.join(f'{k}: {v}' for k, v in manager_stats.most_common())})"
        )
    total = manager_stats.total()
    plural = "s" if total > 1 else ""
    echo(f"{total} package{plural} total{per_manager_totals}.", err=True)


class BarPluginRenderer(MPMPlugin):
    """All utilities used to render output compatible with both Xbar and SwiftBar plugin
    dialect.

    The minimal code to locate ``mpm``, then call it and print its output resides in the
    plugin itself at :py:meth:`meta_package_manager.bar_plugin.MPMPlugin.best_mpm`.

    All other stuff, especially the rendering code, is managed here, to allow for more
    complex layouts relying on external Python dependencies. This also limits the number
    of required updates on the plugin itself.
    """

    @cached_property
    def submenu_layout(self) -> bool:
        """Group packages into manager sub-menus.

        If ``True``, will replace the default flat layout with an alternative structure
        where actions are grouped into submenus, one for each manager.

        Value is sourced from the ``VAR_SUBMENU_LAYOUT`` environment variable.
        """
        return self.getenv_bool("VAR_SUBMENU_LAYOUT", False)

    @cached_property
    def dark_mode(self) -> bool:
        """Detect dark mode by inspecting environment variables.

        Value is sourced from two environment variables depending on the plugin:

        - ``OS_APPEARANCE`` for SwiftBar
        - ``XBARDarkMode`` for XBar
        """
        if self.is_swiftbar:
            return self.getenv_str("OS_APPEARANCE", "light") == "dark"
        return self.getenv_bool("XBARDarkMode")

    @staticmethod
    def render_cli(cmd_args: tuple[str | Path, ...]) -> str:
        """Return a formatted CLI compatible with Xbar and SwiftBar plugin format.

        I.e. a string with this schema:

        .. code-block::

            shell=cmd_args[0] param1=cmd_args[1] param2=cmd_args[2] ...
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

    def _render(self, outdated_data) -> None:
        """Main method implementing the final structured rendering in *Bar plugin
        dialect.

        ..todo::

            Wait for ANSI-aware layout in table to be merged upstream so we can highly
            version differences in bar plugin. See:
            https://github.com/astanin/python-tabulate/pull/184
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
                if table:
                    formatted_lines = render_table(
                        [p[0] for p in table],
                        table_format=TableFormat.ALIGNED,
                        colalign=("left", "right", "center", "left"),
                        disable_numparse=True,
                    ).splitlines()
                else:
                    formatted_lines = []

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
                    f"{submenu}{line}",
                    upgrade_cli,
                    font,
                    "refresh=true",
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
                    logging.warning(
                        f"{theme.invoked_command(manager_id)} "
                        "does not implement upgrade_all_cli.",
                    )
                    mpm_args, _runnable, _up_to_date, _version, _error = self.best_mpm
                    upgrade_all_cli = (
                        *mpm_args,
                        f"--{manager_id}",
                        "upgrade",
                        "--all",
                    )
                    logging.debug(f"Fallback to direct mpm call: {upgrade_all_cli}")

                # Update outdated data with the full-upgrade CLI.
                outdated_data[manager_id]["upgrade_all_cli"] = self.render_cli(
                    upgrade_all_cli,
                )

                # Add for each package its upgrade CLI.
                for package in manager_data["packages"]:
                    # Generate the version-less upgrade CLI to be used by the *bar
                    # plugin.
                    upgrade_cli = None
                    with contextlib.suppress(NotImplementedError):
                        upgrade_cli = self.render_cli(
                            manager.upgrade_one_cli(package["id"]),
                        )

                    package["upgrade_cli"] = upgrade_cli

        return outdated_data

    def print(self, outdated_data) -> None:
        """Print the final plugin rendering to ``<stdout>``.

        Capturing the output of the plugin and re-printing it will introduce an extra
        line return, hence the extra call to ``rstrip()``.
        """
        outdated_data = self.add_upgrade_cli(outdated_data)
        echo(self.render(outdated_data).rstrip())
