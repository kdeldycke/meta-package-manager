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
"""Renderer on the `mpm` side, which builds the SwiftBar and Xbar plugin
output.

This code is in its own module. {mod}`meta_package_manager.bar_plugin` uses
the Python standard library only, because its
{class}`~meta_package_manager.bar_plugin.MPMPlugin` class is the script that
the user installs as the bar plugin, and that script must have few
dependencies.

This module is the companion on the `mpm` side. It adds click_extra, boltons,
the manager pool and the theme system to the plugin code, and produces the
final output of `mpm outdated --plugin-output`.
"""

from __future__ import annotations

import contextlib
import sys
from functools import cached_property
from io import StringIO
from pathlib import Path

from boltons.iterutils import flatten
from boltons.strutils import strip_ansi
from click_extra import echo
from click_extra.color import invocation_color
from click_extra.table import TableFormat, render_table

from .bar_plugin import MPMPlugin
from .capabilities import Operations, implements
from .package import manager_purl
from .pool import pool
from .version import common_prefix_length, diff_versions

MAX_VERSION_WIDTH = 18
"""Maximum width of a version in a menu line, in characters.

A macOS menu cannot scroll sideways and a menu item is one line high, so a row
wider than the menu loses its end. SwiftBar keeps the AppKit default paragraph
style `.byWordWrapping`, which moves the last token to a second line that the
item does not draw. That token is the new version, so one package with a long
version hides the column that the menu shows. The limit also helps the other
rows, because the table aligns on the widest cell of the column.

The value `18` comes from a survey of 1087 version strings: 578 from the
bundled `[samples]` fixtures and the manager docstrings, and 509 from the
inventory of one macOS system. The two groups are far apart. A version that a
person reads is 17 characters long at most (`152.0.7977.82-1.1`, a Homebrew
cask). A machine identifier starts at 26 characters: a Julia build triple, a
commit SHA of 40 characters, and Homebrew's 50-character `version,revision`
pair. `18` is the smallest limit that keeps all of the first group. In the
fixtures, the Linux package managers reach 22 characters
(`2.7+git1722+daf2f52-r0`, an OpenWrt package). This renderer never sees them,
because SwiftBar and Xbar run on macOS only.

Set the `VAR_MAX_VERSION_WIDTH` environment variable to change this value. See
{meth}`BarPluginRenderer.max_version_width`.
"""

VERSION_ELLIPSIS = "…"
"""Marker for the characters that {data}`MAX_VERSION_WIDTH` removes.

It is one character wide in a monospace font, so the table loses one column.
`...` would lose three.
"""

VERSION_PREFIX_COLOR = 245
"""Index in the xterm-256 palette for the unchanged prefix of a version.

The CLI table keeps the default `bright_black` (SGR `90`) of
{func}`meta_package_manager.version.diff_versions`, and a terminal changes that
color to match its own theme. SwiftBar always maps SGR `90` to the fixed
`NSColor.darkGray`, which is hard to see on a dark menu. Its support of 256
colors renders the palette index `245` as a mid-gray (`#8a8a8a`) that does not
depend on the theme and is readable in both appearances. Xbar removes the ANSI
codes that it does not render, so this choice has no effect there.
"""

LIGHT_MENU_OLD_COLOR = 124
"""Palette index for the red suffix of the old version on a light menu.

`#af0000`, with a contrast ratio of `6.5:1` on the cream material. See
{meth}`BarPluginRenderer.menu_diff_colors` for the reason for this value.
"""

LIGHT_MENU_NEW_COLOR = 23
"""Palette index for the green suffix of the new version on a light menu.

`#006600`, with a contrast ratio of `6.3:1` on the cream material. See
{meth}`BarPluginRenderer.menu_diff_colors`.
"""

DARK_MENU_NEW_COLOR = 46
"""Palette index for the green suffix of the new version on a dark menu.

`#00ff00`. It raises the worst contrast from `4.0:1`, the value of the adaptive
`NSColor.systemGreen`, to `5.8:1` when a bright wallpaper shows through the
translucent menu. The red suffix of the old version keeps `systemRed`. It is
already the most readable red in the xterm-256 palette: a pure `#ff0000` has a
lower ratio, and a brighter red looks orange. See
{meth}`BarPluginRenderer.menu_diff_colors`.
"""


def elide_versions(old: str, new: str, width: int) -> tuple[str, str]:
    """Shorten a pair of versions to `width` characters, and keep the two
    versions different.

    The function removes the end of each version first. The end holds the part
    that nobody reads: a commit SHA, a platform triple, or Homebrew's
    `version,revision` pair. That method does not work for a
    rebuild whose last characters are the only difference
    (`2.6.0-2.suse1699.10` against its `.11`), because the two results would be
    the same string with an arrow between them. The function then removes the
    common start instead. It puts the `…` at the boundary that
    {func}`~meta_package_manager.version.common_prefix_length` reports, so the
    marker sits between the gray prefix and the colored suffix.

    The function makes this choice for the pair, and not for each version on
    its own. With a choice per version, one run rendered `5.0.0~beta1-0ubuntu7`
    as `….0~beta1-0ubuntu7` next to `5.0.2-0ubuntu1~26…`, which had kept its
    start. The column did not line up, and one side alone lost its `5.0`.
    """
    if max(len(old), len(new)) <= width:
        return old, new

    budget = width - len(VERSION_ELLIPSIS)
    cut_tail = tuple(
        version if len(version) <= width else version[:budget] + VERSION_ELLIPSIS
        for version in (old, new)
    )
    if cut_tail[0] != cut_tail[1]:
        return cut_tail[0], cut_tail[1]

    # Removing the end made the two versions equal, so remove the common start.
    common = common_prefix_length(old, new)
    elided = []
    for version in (old, new):
        suffix = version[common:]
        head = budget - len(suffix)
        if head > 0:
            elided.append(version[:head] + VERSION_ELLIPSIS + suffix)
        else:
            # No part of the common start fits. This happens when one
            # version fills the whole budget and has no separator to cut on.
            # Keep the end, where the two versions are different.
            elided.append(VERSION_ELLIPSIS + version[-budget:])
    return elided[0], elided[1]


class BarPluginRenderer(MPMPlugin):
    """Renders `mpm outdated` in the SwiftBar and Xbar plugin dialect.

    This class adds the rendering to
    {class}`~meta_package_manager.bar_plugin.MPMPlugin`. The rendering can use
    mpm's own dependencies. See the module docstring for the division
    between the two modules.
    """

    @cached_property
    def group_by_manager(self) -> bool:
        """Give each manager its own section, in place of one flat list.

        Each host draws that section in its own way: Xbar opens a sub-menu,
        SwiftBar folds an accordion into the same menu, and the GNOME Shell
        extension expands the section inline. The name of this option describes
        the grouping itself, and not the way one host draws it.

        The value comes from the `VAR_GROUP_BY_MANAGER` environment variable.
        """
        return self.getenv_bool("VAR_GROUP_BY_MANAGER", True)

    @cached_property
    def fold_sections(self) -> bool:
        """Render the manager sections as inline accordions instead of
        sub-menus.

        SwiftBar `2.1.0` renders an item with `fold=true` and its
        `--`-prefixed children as one collapsible section. A click on the
        header expands the section in place. It does not open a sub-menu and it
        does not close the menu. The expanded state stays after a refresh
        ([swiftbar/SwiftBar#480](https://github.com/swiftbar/SwiftBar/pull/480)).

        This option needs {attr}`group_by_manager`, which provides the children
        to fold. Xbar has no equivalent parameter and ignores it, so its
        grouped layout keeps the sub-menus.
        """
        return self.group_by_manager and self.is_swiftbar

    @cached_property
    def own_panel_per_manager(self) -> bool:
        """`True` when the packages of each manager have a panel of their own.

        This is true for Xbar's grouped layout only, where a
        `--`-prefixed row opens a sub-menu. SwiftBar folds the same rows into
        the same menu, and the flat layout stays in one menu too. In those
        cases every package is in one continuous column.
        """
        return self.group_by_manager and not self.fold_sections

    @cached_property
    def max_version_width(self) -> int:
        """Maximum width of a rendered version, in characters, before the
        renderer shortens it.

        The value comes from the `VAR_MAX_VERSION_WIDTH` environment variable,
        and its default is {data}`MAX_VERSION_WIDTH`. A value lower than `2`
        leaves no space for the ellipsis and for one character of content, so
        the code reads it as no limit.
        """
        width = self.getenv_int("VAR_MAX_VERSION_WIDTH", MAX_VERSION_WIDTH)
        return width if width > 1 else 0

    @cached_property
    def menu_diff_colors(self) -> dict[str, int]:
        """Colors of the version-diff suffixes, adapted to the menu
        appearance.

        SwiftBar maps the default SGR `31` and `32` suffixes of
        {func}`meta_package_manager.version.diff_versions` to the adaptive
        colors `NSColor.systemRed` and `NSColor.systemGreen`. It also puts the
        menu appearance in the `OS_APPEARANCE` environment variable,
        which the `mpm outdated --plugin-output` subprocess inherits. On the
        translucent "Liquid Glass" menus of recent macOS releases, these system
        colors have too little contrast with the material. The method replaces
        them for each appearance:

        - On a **light** menu, both suffixes are too pale. The measured
          contrast of the green is `1.9:1`. The method uses the darker
          {data}`LIGHT_MENU_OLD_COLOR` and {data}`LIGHT_MENU_NEW_COLOR`.
        - On a **dark** menu above a bright wallpaper, the contrast of the green
          falls to `4.0:1`. The method uses the brighter
          {data}`DARK_MENU_NEW_COLOR`, and keeps `systemRed` for the red. That
          red is already the most readable red in the palette.

        The result is a set of keyword arguments for `diff_versions`. The
        method returns an empty mapping when the variable is not set, for a
        host like Xbar that removes these codes. The system colors then stay in
        force.
        """
        appearance = self.getenv_str("OS_APPEARANCE")
        if appearance == "light":
            return {"old_fg": LIGHT_MENU_OLD_COLOR, "new_fg": LIGHT_MENU_NEW_COLOR}
        if appearance == "dark":
            return {"new_fg": DARK_MENU_NEW_COLOR}
        return {}

    @cached_property
    def mpm_cli(self) -> tuple[str, ...]:
        """Absolute `mpm` command that runs the actions of the menu.

        The command starts the same interpreter that renders the menu. A click
        then runs the same `mpm` that the plugin called, and reads the same
        configuration file. The value comes from {data}`sys.executable`, not
        from `sys.argv[0]`. {data}`sys.executable` is always an absolute path to
        a runnable entry point. `sys.argv[0]` can be a console script, a
        `__main__.py` file or a bare `-c`, and it depends on the way `mpm`
        started. An `mpm` compiled with Nuitka is its own interpreter, so the
        code calls it directly, with no module.

        `-P` keeps the folder that the action starts from out of `sys.path`.
        Without it, `-m`
        puts that folder first. An action started from a source checkout would
        then import that source tree, with the dependencies of the installed
        version. A `7.6.1` interpreter that read an `8.0.0.dev0` tree stopped
        on `from click_extra.table import AUTO_WIDTH`. The flag needs Python
        `3.11`. The interpreter that renders the menu is the one that the
        action starts, so its own version decides.

        ```{note}
        This code does not reuse the candidates that
        {meth}`meta_package_manager.bar_plugin.MPMPlugin.search_mpm` produces.
        The candidates from a virtual environment start with a bare `uv`,
        `pipenv` or `poetry` command name. A bar app starts a menu action with
        the `launchd` `PATH` alone, and that `PATH` cannot find such a name.
        ```
        """
        if "__compiled__" in globals():
            return (sys.executable, *self.mpm_options)
        safe_path = ("-P",) if sys.version_info >= (3, 11) else ()
        return (
            sys.executable,
            *safe_path,
            "-m",
            "meta_package_manager",
            *self.mpm_options,
        )

    @staticmethod
    def render_cli(cmd_args: tuple[str | Path, ...]) -> str:
        """Return a command in the SwiftBar and Xbar plugin format.

        The result is a string with this schema:

        ```{code-block}

        shell=cmd_args[0] param1=cmd_args[1] param2=cmd_args[2] ...
        ```
        """
        plugin_params = []
        for index, param_value in enumerate(map(str, flatten(cmd_args))):
            param_id = "shell" if index == 0 else f"param{index}"
            plugin_params.append(f"{param_id}={param_value}")
        return " ".join(plugin_params)

    def print_cli_item(self, *args) -> None:
        """Print two menu entries for one command:

        - one that opens a visible terminal, so the user can follow the
          execution
        - one that runs with no terminal, which the user reaches with the
          `Option` key
        """
        self.pp(*args, "terminal=true")
        self.pp(*args, "terminal=false", "alternate=true")

    def print_upgrade_all_item(self, manager: dict, submenu: str = "") -> None:
        """Print the menu entry that upgrades every outdated package of one
        manager."""
        if manager.get("upgrade_all_cli"):
            if self.group_by_manager:
                print("-----")
            self.print_cli_item(
                f"{submenu}🆙 Upgrade all {manager['id']} packages",
                manager["upgrade_all_cli"],
                self.default_font,
                "refresh=true",
            )

    def package_rows(self, manager) -> list[tuple[tuple[str, ...], str, str]]:
        """Return one row of cells for each outdated package.

        Each result holds the cells, the command that the row runs, and the
        tooltip with the full versions that the width limit removed.
        """
        rows: list[tuple[tuple[str, ...], str, str]] = []
        for package in manager["packages"]:
            # Convert to strings here. The TokenizedString objects in the
            # payload of `mpm outdated` answer len(), but they cannot be
            # sliced, and shortening a version needs a slice.
            full_old = str(package["installed_version"] or "?")
            full_new = str(package["latest_version"])
            old, new = (
                elide_versions(full_old, full_new, self.max_version_width)
                if self.max_version_width
                else (full_old, full_new)
            )
            installed, latest = diff_versions(
                old,
                new,
                prefix_fg=VERSION_PREFIX_COLOR,
                **self.menu_diff_colors,
            )
            # The empty cell is a spacer. In the aligned layout it widens the
            # gap between the longest name and its version from one space to
            # two. In the joined layout it gives the same double space.
            label = package.get("name") or package.get("id")
            rows.append((
                (label, "", installed, "→", latest),
                package["upgrade_cli"],
                self.version_tooltip(full_old, full_new, (old, new)),
            ))
        return rows

    def version_tooltip(self, old: str, new: str, elided: tuple[str, str]) -> str:
        """Return the full version pair for a menu item whose cells were
        shortened.

        SwiftBar shows a `tooltip` when the pointer is above the item, so the
        user can still read the characters that {meth}`max_version_width`
        removed. The SwiftBar parser reads a quoted value as one piece, so the
        spaces around the arrow are safe. Xbar has no such parameter and would
        render the text as part of the label, so the method returns an empty
        string for Xbar.
        """
        if not self.is_swiftbar or (old, new) == elided:
            return ""
        return f'tooltip="{old} → {new}"'

    @staticmethod
    def align_rows(rows: list[tuple[str, ...]]) -> list[str]:
        """Put a set of rows into aligned columns.

        The arrow is centered, so the user follows one vertical line down the
        column, and the versions grow away from it on both sides.
        """
        if not rows:
            return []
        return render_table(
            rows,
            table_format=TableFormat.ALIGNED,
            colalign=("left", "left", "right", "center", "left"),
            disable_numparse=True,
        ).splitlines()

    def align_managers(
        self, rows_by_manager: dict[str, list[tuple[tuple[str, ...], str, str]]]
    ) -> dict[str, list[str]]:
        """Align the rows of every manager, in one table or in one table per
        manager.

        One table serves the layouts where the managers share a column: the
        flat layout and the SwiftBar accordion. A table sized for one manager
        aligns its own arrows, but those arrows then do not line up with the
        section above. In a menu that the user reads in one pass, that looks
        like a mistake.

        One table per manager serves the layouts where each manager has a panel
        of its own. There, a width taken from all the managers would pad every
        short sub-menu to the longest package name in the report.
        """
        if self.own_panel_per_manager:
            return {
                manager_id: self.align_rows([cells for cells, *_ in rows])
                for manager_id, rows in rows_by_manager.items()
            }
        lines = self.align_rows([
            cells for rows in rows_by_manager.values() for cells, *_ in rows
        ])
        aligned, start = {}, 0
        for manager_id, rows in rows_by_manager.items():
            aligned[manager_id] = lines[start : start + len(rows)]
            start += len(rows)
        return aligned

    def _render(self, outdated_data) -> None:
        """Render the whole menu in the bar plugin dialect.

        The version columns use the ANSI colors that
        {func}`meta_package_manager.version.diff_versions` produces: a gray
        common prefix ({data}`VERSION_PREFIX_COLOR`), a red suffix for the old
        version and a green suffix for the new one. {meth}`menu_diff_colors`
        changes the two suffixes to match the appearance of the menu. The table
        stays aligned with these escape codes, because `tabulate` measures a
        line without them
        ([astanin/python-tabulate#184](https://github.com/astanin/python-tabulate/pull/184)).
        The package lines of the menu ask for these colors with the `ansi=true`
        parameter.
        """
        managers = outdated_data.values()
        font = self.monospace_font if self.align_columns else self.default_font

        total_outdated = sum(len(m["packages"]) for m in managers)
        total_errors = sum(len(m.get("errors", [])) for m in managers)

        # The host hides the plugin when the plugin produces no output, so the
        # rendering stops before its first line. Errors keep the icon visible:
        # they are the report, and removing them would hide a broken manager.
        if not self.always_visible and not total_outdated and not total_errors:
            return

        self.pp(
            (f"🎁↑{total_outdated}" if total_outdated else "📦✓")
            + (f" ⚠️{total_errors}" if total_errors else ""),
            "dropdown=false",
        )

        submenu = "--" if self.group_by_manager else ""

        rows_by_manager = {
            manager["id"]: self.package_rows(manager) for manager in managers
        }
        aligned = self.align_managers(rows_by_manager) if self.align_columns else {}

        for manager in managers:
            package_count = len(manager["packages"])
            plural = "s" if package_count > 1 else ""
            package_label = f"package{plural}"
            table = rows_by_manager[manager["id"]]

            # SwiftBar renders the count as a native badge on the section
            # header, so the label does not repeat it. A count of zero gets no
            # badge. The badge is large, so it must show a number that asks for
            # an action. The section itself already tells the user that the
            # plugin queried the manager.
            badge = ""
            if self.is_swiftbar and package_count:
                badge = f"badge={package_count}"

            if self.align_columns:
                header = (
                    manager["id"]
                    if self.is_swiftbar
                    else f"{manager['id']} - {package_count} {package_label}"
                )
                formatted_lines = aligned[manager["id"]]
            else:
                header = (
                    manager["name"]
                    if self.is_swiftbar
                    else f"{package_count} outdated {manager['name']} {package_label}"
                )
                formatted_lines = [" ".join(map(str, cells)) for cells, *_ in table]

            print("---")
            error = "⚠️ " if self.group_by_manager and manager.get("errors") else ""
            self.pp(
                f"{error}{header}",
                font,
                badge,
                "fold=true" if self.fold_sections else "",
            )

            # `ansi=true` renders the colors of the version diff. The default
            # is false in SwiftBar and true in Xbar, so it is always set here.
            for line, (_, upgrade_cli, tooltip) in zip(
                formatted_lines, table, strict=True
            ):
                self.print_cli_item(
                    f"{submenu}{line}",
                    upgrade_cli,
                    font,
                    "ansi=true",
                    tooltip,
                    "refresh=true",
                )

            self.print_upgrade_all_item(manager, submenu)

            for error_msg in manager.get("errors", []):
                print("-----" if self.group_by_manager else "---")
                # The error lines use ansi=false, and the plugin output is
                # printed with the colors forced on. An ANSI code from a
                # manager's own output would then reach the bar app as text.
                self.print_error(strip_ansi(error_msg), submenu)

    def render(self, outdated_data) -> str:
        """Call `_render()` and capture its `<stdout>` output.

        Every method on the `_render` path writes with a plain `print` call,
        and that includes the inherited `pp` and `print_error`. One
        redirection of `<stdout>` then captures the whole rendering.
        """
        capture = StringIO()
        with contextlib.redirect_stdout(capture):
            self._render(outdated_data)
        return capture.getvalue()

    def add_upgrade_cli(self, outdated_data):
        """Add the upgrade commands to the data of `mpm outdated`, for the bar
        plugin.

        Every menu action is one {attr}`mpm_cli` call limited to the manager of
        the section (`mpm --brew upgrade wget`). It is never the native command
        of that manager. A click that goes through `mpm` follows the same
        settings as the run that rendered the menu: the configuration file on
        the system, and with it the release-age cooldown, the manager
        selection, the sudo policy and the per-manager overrides. A native
        command ignores all of them, and would upgrade a package that `mpm`
        would have stopped.

        The command passes only the manager selector, the operation and the
        package. `mpm` reads every other setting from the user's configuration
        at the time of the click. The package is a pURL
        ({func}`~meta_package_manager.package.manager_purl`), which names the
        section's manager. `mpm` then upgrades the package without a
        search in the installed packages. That search misses the packages that
        a manager reports as outdated but not as installed.

        A manager gets the action only when it
        {func}`~meta_package_manager.capabilities.implements` it. This is the
        same test that `mpm` uses to route the subcommand. A manager that
        `mpm` would skip gets a `None` command, and the menu renders its label
        alone.
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

            upgrades_one = implements(manager, Operations.upgrade)
            for package in manager_data["packages"]:
                package["upgrade_cli"] = None
                if upgrades_one:
                    package["upgrade_cli"] = self.render_cli(
                        (
                            *self.mpm_cli,
                            selector,
                            "upgrade",
                            manager_purl(manager_id, package["id"]),
                        ),
                    )

        return outdated_data

    def print(self, outdated_data) -> None:
        """Print the final plugin rendering to `<stdout>`.

        Capturing the output and printing it again would add one line break,
        so the call to `rstrip()` removes it.

        The colors are forced on, and `echo` does not run its own detection.
        The bar plugin captures `mpm outdated --plugin-output` through a pipe,
        and `echo` would remove every ANSI code there. The colors of the
        version diff would then never reach SwiftBar or Xbar. A TTY test has no
        meaning for this dialect, which sets the rendering of ANSI codes line
        by line with the `ansi=true` and `ansi=false` parameters. An explicit
        opt-out (`--color=never`, `NO_COLOR`) still applies: the code replaces
        the automatic (`None`) state only. The value comes from
        {func}`~click_extra.color.invocation_color`, not from `ctx.color`, so it
        is also correct for a rendering on a worker thread. The command context
        is thread-local and does not reach such a thread.
        """
        outdated_data = self.add_upgrade_cli(outdated_data)
        color = invocation_color()
        echo(
            self.render(outdated_data).rstrip(),
            color=True if color is None else color,
        )
