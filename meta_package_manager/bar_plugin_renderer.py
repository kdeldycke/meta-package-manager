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
"""mpm-side renderer that builds Xbar/SwiftBar plugin output.

Lives in its own module rather than in
{mod}`meta_package_manager.bar_plugin` because that module is
intentionally stdlib-only: the
{class}`meta_package_manager.bar_plugin.MPMPlugin` class is the
script that gets installed as the user's actual bar plugin and must
stay light on dependencies.

This module is the heavier mpm-side companion that augments the
shippable plugin code with click_extra, boltons, the manager pool, and
the theme system to produce the final rendered output from
`mpm outdated --plugin-output`.
"""

from __future__ import annotations

import contextlib
import sys
from functools import cached_property
from io import StringIO
from pathlib import Path

from boltons.iterutils import flatten
from boltons.strutils import strip_ansi
from click_extra import echo, get_current_context
from click_extra.table import TableFormat, render_table

from .bar_plugin import MPMPlugin
from .capabilities import Operations, implements
from .pool import pool
from .version import diff_versions

VERSION_PREFIX_COLOR = 245
"""Xterm-256 palette index coloring the unchanged version prefix in menu lines.

The CLI table keeps {func}`meta_package_manager.version.diff_versions`'s default
`bright_black` (SGR `90`), which terminals remap to their own theme. SwiftBar
instead hard-maps SGR `90` to a fixed `NSColor.darkGray`, near-invisible on a
dark-mode menu, while its 256-color support renders palette index `245` as a
theme-neutral mid-gray (`#8a8a8a`), legible on both appearances. Xbar strips
the ANSI codes it does not render, so the choice is inert there.
"""

LIGHT_MENU_OLD_COLOR = 124
"""Palette index for the old-version (red) suffix on a light-appearance menu.

`#af0000`, a `6.5:1` contrast ratio on the cream material. See
{meth}`BarPluginRenderer.menu_diff_colors` for why the override exists.
"""

LIGHT_MENU_NEW_COLOR = 23
"""Palette index for the new-version (green) suffix on a light-appearance menu.

`#006600`, a `6.3:1` contrast ratio on the cream material. See
{meth}`BarPluginRenderer.menu_diff_colors`.
"""

DARK_MENU_NEW_COLOR = 46
"""Palette index for the new-version (green) suffix on a dark-appearance menu.

`#00ff00`, lifting the worst-case contrast from `4.0:1` (the adaptive
`NSColor.systemGreen`) to `5.8:1` over a bright wallpaper showing through the
translucent menu. The old-version (red) suffix keeps `systemRed`: it is already
the most readable recognizable red the xterm-256 palette can express (a pure
`#ff0000` scores lower, and brighter options read as orange). See
{meth}`BarPluginRenderer.menu_diff_colors`.
"""


class BarPluginRenderer(MPMPlugin):
    """All utilities used to render output compatible with both Xbar and SwiftBar plugin
    dialect.

    The minimal code to locate `mpm`, then call it and print its output resides in the
    plugin itself at {meth}`meta_package_manager.bar_plugin.MPMPlugin.best_mpm`.

    All other stuff, especially the rendering code, is managed here, to allow for more
    complex layouts relying on external Python dependencies. This also limits the number
    of required updates on the plugin itself.
    """

    @cached_property
    def submenu_layout(self) -> bool:
        """Group packages into manager sub-menus.

        If `True`, will replace the default flat layout with an alternative structure
        where actions are grouped into submenus, one for each manager.

        Value is sourced from the `VAR_SUBMENU_LAYOUT` environment variable.
        """
        return self.getenv_bool("VAR_SUBMENU_LAYOUT", False)

    @cached_property
    def fold_sections(self) -> bool:
        """Render manager sections as inline accordions instead of sub-menus.

        SwiftBar `2.1.0` renders an item carrying `fold=true` alongside its
        `--`-prefixed children as a collapsible section: clicking the header
        expands it in place rather than opening a sub-menu, without dismissing
        the menu, and the expanded state survives a refresh
        ([swiftbar/SwiftBar#480](https://github.com/swiftbar/SwiftBar/pull/480)).

        Depends on {attr}`submenu_layout` for the children it folds. Xbar has no
        equivalent and ignores the parameter, so the grouped layout keeps its
        sub-menus there.
        """
        return self.submenu_layout and self.is_swiftbar

    @cached_property
    def menu_diff_colors(self) -> dict[str, int]:
        """Appearance-adaptive version-diff suffix colors for the menu.

        SwiftBar maps {func}`meta_package_manager.version.diff_versions`'s
        default SGR `31`/`32` suffixes to the *adaptive*
        `NSColor.systemRed`/`systemGreen`, and exports the menu appearance in
        the `OS_APPEARANCE` environment variable (which propagates to the `mpm
        outdated --plugin-output` subprocess). On the translucent "Liquid
        Glass" menus of recent macOS releases these system colors lose contrast
        against the material, so override them per appearance:

        - A **light** menu washes out both suffixes (the green measured
          `1.9:1`), so darken them to {data}`LIGHT_MENU_OLD_COLOR` and
          {data}`LIGHT_MENU_NEW_COLOR`.
        - A **dark** menu over a bright wallpaper dims the green to `4.0:1`, so
          brighten it to {data}`DARK_MENU_NEW_COLOR`; the red keeps `systemRed`,
          already the most readable red the palette allows.

        The result is returned as `diff_versions` keyword arguments. When the
        variable is absent (a consumer like Xbar, which strips these codes
        anyway) return an empty mapping, keeping the system-color defaults.
        """
        appearance = self.getenv_str("OS_APPEARANCE")
        if appearance == "light":
            return {"old_fg": LIGHT_MENU_OLD_COLOR, "new_fg": LIGHT_MENU_NEW_COLOR}
        if appearance == "dark":
            return {"new_fg": DARK_MENU_NEW_COLOR}
        return {}

    @cached_property
    def mpm_cli(self) -> tuple[str, ...]:
        """Absolute `mpm` invocation the menu actions are routed through.

        Re-enters the very interpreter rendering the menu, so a click runs the
        `mpm` the plugin called and resolves the same configuration file. Derived
        from {data}`sys.executable` rather than `sys.argv[0]`: the former is always
        an absolute path to a runnable entry point, while the latter degrades to a
        console script, a `__main__.py` or a bare `-c` depending on how `mpm` was
        started. A Nuitka-compiled `mpm` is its own interpreter, so it is invoked
        directly instead of through the module.

        ```{note}
        The candidates
        {meth}`meta_package_manager.bar_plugin.MPMPlugin.search_mpm` produces are
        deliberately not reused here. The venv ones lead with a bare `uv` /
        `pipenv` / `poetry` command name, while a bar app spawns a menu action
        with the bare `launchd` `PATH`, where such a name does not resolve.
        ```
        """
        if "__compiled__" in globals():
            return (sys.executable,)
        return (sys.executable, "-m", "meta_package_manager")

    @staticmethod
    def render_cli(cmd_args: tuple[str | Path, ...]) -> str:
        """Return a formatted CLI compatible with Xbar and SwiftBar plugin format.

        I.e. a string with this schema:

        ```{code-block}

        shell=cmd_args[0] param1=cmd_args[1] param2=cmd_args[2] ...
        ```
        """
        plugin_params = []
        # Serialize Path into string.
        for index, param_value in enumerate(map(str, flatten(cmd_args))):
            param_id = "shell" if index == 0 else f"param{index}"
            plugin_params.append(f"{param_id}={param_value}")
        return " ".join(plugin_params)

    def print_cli_item(self, *args) -> None:
        """Print two CLI entries:

        - one that opens a visible terminal so the user can follow the execution
        - a second one, reachable by holding the `Option` key, that runs silently
        """
        self.pp(*args, "terminal=true")
        self.pp(*args, "terminal=false", "alternate=true")

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

        Version columns carry the ANSI colors produced by
        {func}`meta_package_manager.version.diff_versions`: common prefix
        gray ({data}`VERSION_PREFIX_COLOR`), old suffix red, new suffix
        green, the suffixes recolored per menu appearance by
        {meth}`menu_diff_colors`. Table alignment survives the escape
        codes thanks to `tabulate`'s ANSI-aware layout
        ([astanin/python-tabulate#184](https://github.com/astanin/python-tabulate/pull/184)), and package
        menu lines opt into rendering them with the `ansi=true` parameter.
        """
        managers = outdated_data.values()
        font = self.monospace_font if self.table_rendering else self.default_font

        # Print menu bar icon with number of available upgrades.
        total_outdated = sum(len(m["packages"]) for m in managers)
        total_errors = sum(len(m.get("errors", [])) for m in managers)

        # Producing no output is what makes the host hide the plugin, so the
        # rendering stops before its first line. Errors keep the icon around:
        # they are the report, and silencing them would hide a broken manager.
        if self.hide_when_up_to_date and not total_outdated and not total_errors:
            return

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

            table = []
            for p in manager["packages"]:
                installed, latest = diff_versions(
                    p["installed_version"] if p["installed_version"] else "?",
                    p["latest_version"],
                    prefix_fg=VERSION_PREFIX_COLOR,
                    **self.menu_diff_colors,
                )
                # The empty cell is a spacer, and it earns its place in both
                # renderings. Aligned, the longest name would otherwise sit one
                # space from its version, too tight to read a package apart from
                # what it upgrades to; the spacer column widens that gap to two
                # without disturbing the alignment of the rest. Joined for the
                # variable-width rendering, it falls out as the same double
                # space between the two halves of the row.
                table.append((
                    (p.get("name") or p.get("id"), "", installed, "→", latest),
                    p["upgrade_cli"],
                ))

            # SwiftBar renders the count as a native badge on the section
            # header, so the label drops the copy it would duplicate. A zero
            # earns no badge: the pill is prominent enough that it should only
            # ever carry an actionable count, and the section is itself proof
            # the manager was queried.
            badge = ""
            if self.is_swiftbar and package_count:
                badge = f"badge={package_count}"

            # Table-like rendering
            if self.table_rendering:
                header = (
                    manager["id"]
                    if self.is_swiftbar
                    else f"{manager['id']} - {package_count} {package_label}"
                )
                if table:
                    formatted_lines = render_table(
                        [p[0] for p in table],
                        table_format=TableFormat.ALIGNED,
                        colalign=("left", "left", "right", "center", "left"),
                        disable_numparse=True,
                    ).splitlines()
                else:
                    formatted_lines = []

            # Variable-width / non-table / non-monospaced rendering.
            else:
                header = (
                    manager["name"]
                    if self.is_swiftbar
                    else f"{package_count} outdated {manager['name']} {package_label}"
                )
                formatted_lines = [" ".join(map(str, p[0])) for p in table]

            upgrade_cli_list = [p[1] for p in table]

            assert len(formatted_lines) == len(upgrade_cli_list)

            # Print section separator before printing the manager header.
            print("---")

            # Print section header.
            error = ""
            if self.submenu_layout and manager.get("errors", None):
                error = "⚠️ "
            self.pp(
                f"{error}{header}",
                font,
                badge,
                "fold=true" if self.fold_sections else "",
            )

            # Print a menu entry for each outdated packages. The ansi=true
            # parameter renders the version-diff colors; SwiftBar defaults it
            # to false, Xbar to true, so it is always spelled out.
            for line, upgrade_cli in zip(formatted_lines, upgrade_cli_list):
                self.print_cli_item(
                    f"{submenu}{line}",
                    upgrade_cli,
                    font,
                    "ansi=true",
                    "refresh=true",
                )

            self.print_upgrade_all_item(manager, submenu)

            for error_msg in manager.get("errors", []):
                print("-----" if self.submenu_layout else "---")
                # Error lines are marked ansi=false, and plugin output is
                # echoed with colors forced, so any ANSI code captured from a
                # manager's own output would reach the bar app as raw text.
                self.print_error(strip_ansi(error_msg), submenu)

    def render(self, outdated_data) -> str:
        """Wraps the `_render()` method above to capture its `<stdout>` output.

        Every producer down the `_render` path (the inherited `pp` and
        `print_error` included) writes through bare `print` calls, so
        redirecting `<stdout>` captures the whole rendering.
        """
        capture = StringIO()
        with contextlib.redirect_stdout(capture):
            self._render(outdated_data)
        return capture.getvalue()

    def add_upgrade_cli(self, outdated_data):
        """Augment the outdated data from `mpm outdated` subcommand with upgrade CLI
        fields for bar plugin consumption.

        Every menu action is an {attr}`mpm_cli` invocation restricted to the manager
        owning the section (`mpm --brew upgrade wget`), never that manager's own
        native command. Going back through `mpm` is what subjects a click to the
        same policy as the run that rendered the menu: the configuration file found
        on the system, and with it the release-age cooldown, the manager
        selection, the sudo policy and the per-manager overrides. A native command
        escapes all of them, silently upgrading a package `mpm` itself would have
        held back.

        Only the manager selector and the operation are passed, so every other
        setting is resolved from the user's configuration at click time.

        A manager is offered the action only when it
        {func}`~meta_package_manager.capabilities.implements` it, which is the same
        predicate `mpm` uses to route the subcommand: a manager it would skip gets
        a `None` CLI and renders as a label-only menu line.
        """
        for manager_id, manager_data in outdated_data.items():
            if not manager_data.get("packages"):
                continue
            manager = pool.get(manager_id)
            selector = f"--{manager_id}"

            manager_data["upgrade_all_cli"] = None
            if implements(manager, Operations.upgrade_all):
                manager_data["upgrade_all_cli"] = self.render_cli(
                    (*self.mpm_cli, selector, "upgrade", "--all"),
                )

            # Add for each package its version-less upgrade CLI.
            upgrades_one = implements(manager, Operations.upgrade)
            for package in manager_data["packages"]:
                package["upgrade_cli"] = None
                if upgrades_one:
                    package["upgrade_cli"] = self.render_cli(
                        (*self.mpm_cli, selector, "upgrade", package["id"]),
                    )

        return outdated_data

    def print(self, outdated_data) -> None:
        """Print the final plugin rendering to `<stdout>`.

        Capturing the output of the plugin and re-printing it will introduce an extra
        line return, hence the extra call to `rstrip()`.

        Colors are forced on `echo`'s auto-detection: the bar plugin captures
        `mpm outdated --plugin-output` through a pipe, where `echo` would
        strip every ANSI code and the version-diff colors would never reach
        SwiftBar or Xbar. TTY detection is meaningless for this dialect, which
        flags ANSI rendering per line with the `ansi=true`/`ansi=false`
        parameters. An explicit opt-out (`--color=never`, `NO_COLOR`) is still
        honored: only the automatic (`None`) state is overridden.
        """
        outdated_data = self.add_upgrade_cli(outdated_data)
        ctx = get_current_context(silent=True)
        color = ctx.color if ctx else None
        echo(
            self.render(outdated_data).rstrip(),
            color=True if color is None else color,
        )
