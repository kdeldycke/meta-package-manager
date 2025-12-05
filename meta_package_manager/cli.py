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

from __future__ import annotations

import logging
import sys
from collections import Counter, namedtuple
from collections.abc import Iterable
from configparser import RawConfigParser
from datetime import datetime
from functools import partial
from io import TextIOWrapper
from operator import attrgetter
from pathlib import Path
from textwrap import dedent
from unittest.mock import patch

import tomli_w
from boltons.cacheutils import LRI, cached
from click_extra import (
    STRING,
    Choice,
    EnumChoice,
    File,
    IntRange,
    Section,
    argument,
    echo,
    file_path,
    group,
    option,
    option_group,
    pass_context,
)
from click_extra.colorize import KO, OK, highlight
from click_extra.colorize import default_theme as theme
from click_extra.commands import default_extra_params
from click_extra.table import TableFormatOption
from extra_platforms import reduce

from . import __version__, bar_plugin
from .base import (
    CLIError,
    Operations,
    PackageManager,
    highlight_cli_name,
    packages_asdict,
)
from .inventory import MAIN_PLATFORMS
from .output import (
    BarPluginRenderer,
    ExtendedTableFormat,
    SortableField,
    SortedTableFormatOption,
    colored_diff,
    print_json,
    print_stats,
)
from .pool import pool
from .sbom import SBOM, SPDX, CycloneDX, ExportFormat
from .specifier import VERSION_SEP, Solver, Specifier

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import IO

    from click_extra import Context, Parameter


# Subcommand sections.
EXPLORE = Section("Explore subcommands")
MAINTENANCE = Section("Maintenance subcommands")
SNAPSHOTS = Section("Package snapshots subcommands")
SBOM_SECTION = Section("SBOM subcommands")


XKCD_MANAGER_ORDER = ("pip", "brew", "npm", "dnf", "apt", "steamcmd")
"""Sequence of package managers as defined by `XKCD #1654: Universal Install Script
<https://xkcd.com/1654/>`_.

See the corresponding :issue:`implementation rationale in issue #10 <10>`.
"""


def is_stdout(filepath: Path) -> bool:
    """Check if a file path is set to stdout.

    Prevents the creation of a ``-`` file in the current directory.
    """
    return str(filepath) == "-"


def prep_path(filepath: Path) -> IO | None:
    """Prepare the output file parameter for Click's echo function."""
    if is_stdout(filepath):
        return None
    return filepath.open("w", encoding="UTF-8")


def update_manager_selection(
    ctx: Context, param: Parameter, value: str | Iterable[str] | bool | None
) -> None:
    """Update global selection list of managers in the context.

    Accumulate and merge all manager selectors to form the initial population enforced by the user.
    """
    # Option has not been called.
    if value is None:
        return

    # Use a list to keep the natural order of selection.
    to_add: list[str] = []
    # Use a set because removal takes precedence over addition: we don't care
    # about user's order.
    to_remove: set[str] = set()

    assert param.name

    # Add the value of --manager list.
    if param.name == "manager":
        if value:
            assert isinstance(value, Iterable)
            to_add.extend(value)

    # Add the value of --exclude list.
    elif param.name == "exclude":
        if value:
            assert isinstance(value, Iterable)
            to_remove.update(value)

    # Update the list of managers with the XKCD preset.
    elif param.name == "xkcd":
        if value:
            to_add.extend(XKCD_MANAGER_ORDER)

    # Update selection with single selectors.
    else:
        # Because the parameter's name is transformed into a Python identifier on
        # instantiation, we have to reverse the process to get our value.
        # Example: --apt-mint => apt_mint => apt-mint
        manager_id = param.name.removeprefix("no_").replace("_", "-")
        assert manager_id in pool.all_manager_ids, (
            f"unrecognized single manager selector {param.name!r}"
        )

        # Normalize the value to a boolean.
        if isinstance(value, str):
            value = RawConfigParser.BOOLEAN_STATES.get(value.lower(), value)
        assert value in (
            manager_id,
            True,
            False,
        ), f"unexpected value {value!r} for {param!r}"

        if param.name.startswith("no_") ^ (value is False):
            to_remove.add(manager_id)
        else:
            to_add.append(manager_id)

    logging.debug(f"Managers added by {param}: {to_add}")
    logging.debug(f"Managers removed by {param}: {to_remove}")

    # Initialize the shared context object to accumulate there the selection results.
    if ctx.obj is None:
        ctx.obj = {}
    if to_add:
        ctx.obj.setdefault("managers_to_add", []).extend(to_add)
    if to_remove:
        ctx.obj.setdefault("managers_to_remove", set()).update(to_remove)


def single_manager_selectors():
    """Dynamiccaly creates a dedicated flag selector alias for each manager."""
    single_flags = []
    single_no_flags = []
    for manager_id, manager in pool.items():
        # Parameters do not have a deprecated flag.
        # See: https://github.com/pallets/click/issues/2263
        deprecated_msg = "(Deprecated) " if manager.deprecated else ""
        single_flags.append(
            option(
                f"--{manager_id}",
                flag_value=manager_id,
                default=None,
                help=f"{deprecated_msg}Select {manager.name}.",
                expose_value=False,
                callback=update_manager_selection,
            )
        )
        single_no_flags.append(
            option(
                f"--no-{manager_id}",
                flag_value=manager_id,
                default=None,
                help=f"{deprecated_msg}Deselect {manager.name}.",
                expose_value=False,
                callback=update_manager_selection,
            )
        )
    return *single_flags, *single_no_flags


def bar_plugin_path(ctx: Context, param: Parameter, value: str | None):
    """Print the location of the :doc:`Xbar/SwiftBar plugin <bar-plugin>`.

    Returns the normalized path of the standalone `bar_plugin.py
    <https://github.com/kdeldycke/meta-package-manager/meta_package_manager/bar_plugin.py>`_
    script that is distributed with this Python module. This
    is made available under the :option:`mpm --bar-plugin-path` option.

    Notice that the fully-qualified home directory get replaced by its
    shorthand (``~``) if applicable:

    - the full ``/home/user/.python/site-packages/mpm/bar_plugin.py`` path is
      simplified to ``~/.python/site-packages/mpm/bar_plugin.py``,
    - but ``/usr/bin/python3.10/mpm/bar_plugin.py`` is returned as-is.
    """
    # Option has not been called.
    if not value:
        return

    # Options is only available when CLI is installed from sources, not CLI is
    # a bundled executable.
    if "__compiled__" in globals():
        logging.debug("CLI running as a binary.")
        logging.critical(
            "Option --bar-plugin-path is only available for CLI installed from "
            "sources.",
        )
        ctx.exit(2)

    bar_path = Path(bar_plugin.__file__).expanduser().resolve()
    home_dir = Path.home()

    if bar_path.is_relative_to(home_dir):
        home_shorthand = Path("~")
        shorten_bar_path = home_shorthand / bar_path.relative_to(home_dir)
        assert shorten_bar_path.expanduser().resolve() == bar_path
        bar_path = shorten_bar_path
    echo(bar_path)
    ctx.exit()


# XXX Why is Sphinx skipping Click methods in documentation?

# Add a help subcommand:
# npm help <term>    search for help on <term>
# npm help npm       more involved overview


#    -j N, --jobs=N      Specify the allowed number of parallel C compiler
#                        jobs. Defaults to the system CPU count.


def custom_extra_params() -> list[Parameter]:
    """Replace the default ``TableFormatOption`` with our ``SortedTableFormatOption``."""
    params: list[Parameter] = []
    for param in default_extra_params():
        if isinstance(param, TableFormatOption):
            params.append(
                SortedTableFormatOption(
                    param_decls=("-o", "--output-format"),
                    type=EnumChoice(ExtendedTableFormat),
                    help="Rendering format of the output.",
                )
            )
        else:
            params.append(param)
    return params


@group(
    # XXX Default verbosity has been changed in Click Extra 4.0.0 from INFO to WARNING.
    context_settings={"default_map": {"verbosity": "INFO"}},
    params=custom_extra_params(),
)
@option_group(
    "Package manager selection",
    # ---------------------- 80 characters reference limit ----------------------- #
    dedent("""\
    \b
    Use these options to restrict the subcommand to a subset of managers.

    \b
    - By default, mpm will evaluate all managers supported on the current platform.
    - Use the --<manager-id> selectors to restrict target to a subset of managers.
    - To remove a manager from the selection, use --no-<manager-id> selectors.
    - Order of the selectors is preserved for priority-sensitive subcommands.
    - Exclusion of a manager always takes precedence over its inclusion.
    \b

    """),
    *single_manager_selectors(),
    option(
        "-a",
        "--all-managers",
        is_flag=True,
        default=False,
        help="Force evaluation of all managers implemented by mpm, including those "
        "not supported by the current platform or deprecated. Still applies filtering "
        "by --<manager-id> / --no-<manager-id> options before calling the subcommand.",
    ),
    option(
        "-x",
        "--xkcd",
        is_flag=True,
        default=None,
        expose_value=False,
        callback=update_manager_selection,
        help="Preset manager selection as defined by XKCD #1654. Equivalent to: "
        "{}.".format(" ".join(f"--{mid}" for mid in XKCD_MANAGER_ORDER)),
    ),
    option(
        "-m",
        "--manager",
        type=Choice(pool.all_manager_ids, case_sensitive=False),
        multiple=True,
        default=None,
        expose_value=False,
        hidden=True,
        callback=update_manager_selection,
        help="(Deprecated) Use --<manager-id> single selector instead.",
    ),
    option(
        "-e",
        "--exclude",
        type=Choice(pool.all_manager_ids, case_sensitive=False),
        multiple=True,
        default=None,
        expose_value=False,
        hidden=True,
        callback=update_manager_selection,
        help="(Deprecated) Use --no-<manager-id> single selector instead.",
    ),
)
@option_group(
    "Manager options",
    option(
        "--ignore-auto-updates/--include-auto-updates",
        default=True,
        help="Report all outdated packages, including those tagged as "
        "auto-updating. Only applies to outdated and upgrade subcommands.",
    ),
    option(
        "--stop-on-error/--continue-on-error",
        default=False,
        help="Stop right away or continue operations on manager CLI error.",
    ),
    option(
        "-d",
        "--dry-run",
        is_flag=True,
        default=False,
        help="Do not actually perform any action, just simulate CLI calls.",
    ),
    option(
        "-t",
        "--timeout",
        type=IntRange(min=0),
        default=500,
        help="Set maximum duration in seconds for each CLI call.",
    ),
)
@option_group(
    "Output options",
    option(
        "--description",
        is_flag=True,
        default=False,
        help="Show package description in results.",
    ),
    option(
        "-s",
        "--sort-by",
        type=EnumChoice(SortableField),
        default=SortableField.MANAGER_ID,
        help="Sort results.",
    ),
    # option('--sort-asc/--sort-desc', default=True)
    option(
        "--stats/--no-stats",
        default=True,
        help="Print per-manager package statistics.",
    ),
)
@option_group(
    "Xbar/SwiftBar options",
    option(
        "--bar-plugin-path",
        is_flag=True,
        default=False,
        expose_value=False,
        is_eager=True,
        callback=bar_plugin_path,
        help="Print location of the Xbar/SwiftBar plugin.",
    ),
)
@pass_context
def mpm(
    ctx,
    all_managers,
    ignore_auto_updates,
    stop_on_error,
    dry_run,
    timeout,
    description,
    sort_by,
    stats,
):
    """CLI options shared by all subcommands."""
    # Silence all log messages for JSON rendering unless in debug mode.
    if (
        ctx.meta["click_extra.table_format"] == ExtendedTableFormat.JSON
        and ctx.meta["click_extra.verbosity"] != "DEBUG"
    ):
        logging.disable()

        def remove_logging_override():
            """Reset the logging override to its default state.

            ``logging.disable()`` mess with the logging module internals at the root
            level. We need to restore the default behavior when the context is closed,
            otherwise the logging module will be stuck in a disabled state.

            See: https://docs.python.org/3/library/logging.html?highlight=logging#logging.disable
            """
            logging.disable(logging.NOTSET)

        ctx.call_on_close(remove_logging_override)

    # Normalize to None if no manager selectors have been used. This prevent the
    # pool.select_managers() method to iterate over an empty population of managers to
    # choose from.
    user_selection = None
    managers_to_remove = None
    if ctx.obj:
        user_selection = ctx.obj.get("managers_to_add", None)
        managers_to_remove = ctx.obj.get("managers_to_remove", None)
    selection_string = (
        " platform default"
        if not user_selection
        else "> " + " > ".join(map(theme.invoked_command, user_selection))
    )
    deselection_string = (
        "None"
        if not managers_to_remove
        else ", ".join(map(theme.invoked_command, sorted(managers_to_remove)))
    )
    logging.info(f"User selection of managers by priority:{selection_string}")
    logging.info(f"Managers dropped by user: {deselection_string}")

    # Select the subset of manager to target, and apply manager-level options.
    selected_managers = partial(
        pool.select_managers,
        keep=user_selection,
        drop=managers_to_remove,
        keep_deprecated=all_managers,
        # Should we include auto-update packages or not?
        ignore_auto_updates=ignore_auto_updates,
        # Does the manager should raise on error or not.
        stop_on_error=stop_on_error,
        dry_run=dry_run,
        timeout=timeout,
    )

    # Load up current and new global options to the context for subcommand consumption.
    ctx.obj = namedtuple(
        "GlobalOptions",
        (
            "selected_managers",
            "description",
            "sort_by",
            "stats",
        ),
        defaults=(
            selected_managers,
            description,
            sort_by,
            stats,
        ),
    )()


@mpm.command(
    short_help="List supported package managers and their location.",
    section=EXPLORE,
)
@pass_context
def managers(ctx):
    """List all supported package managers and autodetect their presence on the
    system."""
    select_params = {
        # Do not drop inactive managers. Keep them to show off how mpm is reacting
        # to the local platform.
        "drop_inactive": False,
    }

    # Machine-friendly data rendering.
    if ctx.meta["click_extra.table_format"] == ExtendedTableFormat.JSON:
        manager_data = {}
        # Build up the data structure of manager metadata.
        fields = (
            "name",
            "id",
            "supported",
            "cli_path",
            "executable",
            "version",
            "fresh",
            "available",
        )
        for manager in ctx.obj.selected_managers(**select_params):
            manager_data[manager.id] = {fid: getattr(manager, fid) for fid in fields}
            # Serialize errors at the last minute to gather all we encountered.
            manager_data[manager.id]["errors"] = list(
                {expt.error for expt in manager.cli_errors},
            )

        print_json(manager_data)
        ctx.exit()

    # Human-friendly content rendering.
    table = []
    for manager in ctx.obj.selected_managers(**select_params):
        # Build up the OS column content.
        os_infos = OK if manager.supported else KO
        if not manager.supported:
            os_infos += " {}".format(
                ", ".join(
                    sorted(p.name for p in reduce(manager.platforms, MAIN_PLATFORMS))
                ),
            )
        if manager.deprecated:
            os_infos += f" {theme.warning('(deprecated)')}"

        # Build up the CLI path column content.
        cli_infos = "{} {}".format(
            OK if manager.cli_path else KO,
            highlight_cli_name(manager.cli_path, manager.cli_names)
            if manager.cli_path
            else (
                f"{', '.join(map(theme.invoked_command, manager.cli_names))} not found"
            ),
        )

        # Build up the version column content.
        version_infos = ""
        if manager.executable:
            version_infos = OK if manager.fresh else KO
            if manager.version:
                version_infos += f" {manager.version}"
                if not manager.fresh:
                    version_infos += f" {manager.requirement}"

        table.append(
            (
                getattr(theme, "success" if manager.fresh else "error")(manager.id),
                manager.name,
                os_infos,
                cli_infos,
                OK if manager.executable else "",
                version_infos,
            ),
        )

    ctx.find_root().print_table(
        (
            ("Manager ID", SortableField.MANAGER_ID),
            ("Name", SortableField.MANAGER_NAME),
            ("Supported", None),
            ("CLI", None),
            ("Executable", None),
            ("Version", SortableField.VERSION),
        ),
        table,
        ctx.obj.sort_by,
    )


@mpm.command(aliases=["list"], short_help="List installed packages.", section=EXPLORE)
@option(
    "-d",
    "--duplicates",
    is_flag=True,
    default=False,
    help="Only list installed packages sharing the same ID. Implies "
    "`--sort_by package_id` to make duplicates easier to compare between themselves.",
)
@pass_context
def installed(ctx, duplicates):
    """List all packages installed on the system by each manager."""
    # Build-up a global dict of installed packages per manager.
    installed_data = {}
    fields = (
        "id",
        "name",
        "installed_version",
    )

    for manager in ctx.obj.selected_managers(implements_operation=Operations.installed):
        packages = tuple(packages_asdict(manager.installed, fields))

        installed_data[manager.id] = {
            "id": manager.id,
            "name": manager.name,
            "packages": packages,
        }

        # Serialize errors at the last minute to gather all we encountered.
        installed_data[manager.id]["errors"] = list(
            {expt.error for expt in manager.cli_errors},
        )

    # Filters out non-duplicate packages.
    if duplicates:
        # Re-group packages by their IDs.
        package_sources = {}
        for manager_id, installed_pkg in installed_data.items():
            for package in installed_pkg["packages"]:
                package_sources.setdefault(package["id"], set()).add(manager_id)
        logging.debug(f"Managers sourcing each package: {package_sources}")

        # Identify package IDs shared by multiple managers.
        duplicates_ids = {
            pid for pid, managers in package_sources.items() if len(managers) > 1
        }
        logging.debug(f"Duplicates: {duplicates_ids}")

        # Remove non-duplicates from results.
        for manager_id in installed_data:
            duplicate_packages = tuple(
                p
                for p in installed_data[manager_id]["packages"]
                if p["id"] in duplicates_ids
            )
            installed_data[manager_id]["packages"] = duplicate_packages

    # Machine-friendly data rendering.
    if ctx.meta["click_extra.table_format"] == ExtendedTableFormat.JSON:
        print_json(installed_data)
        ctx.exit()

    # Human-friendly content rendering.
    table = []
    for manager_id, installed_pkg in installed_data.items():
        table += [
            (
                info["id"],
                info["name"],
                manager_id,
                info["installed_version"] if info["installed_version"] else "?",
            )
            for info in installed_pkg["packages"]
        ]

    # Force sorting by package ID in duplicate mode.
    sort_by = ctx.obj.sort_by
    if duplicates:
        logging.info(
            "Force table sorting on package ID because of --duplicates option."
        )
        sort_by = SortableField.PACKAGE_ID

    # Print table.
    ctx.find_root().print_table(
        (
            ("Package ID", SortableField.PACKAGE_ID),
            ("Name", SortableField.PACKAGE_NAME),
            ("Manager", SortableField.MANAGER_ID),
            ("Installed version", SortableField.VERSION),
        ),
        table,
        sort_by,
    )

    if ctx.obj.stats:
        print_stats(Counter({k: len(v["packages"]) for k, v in installed_data.items()}))


@mpm.command(short_help="List outdated packages.", section=EXPLORE)
@option(
    "--plugin-output",
    is_flag=True,
    default=False,
    help="Output results for direct consumption by an Xbar/SwiftBar-compatible plugin. "
    "The layout is dynamic and depends on environment variables set by either Xbar "
    "or SwiftBar.",
)
@pass_context
def outdated(ctx, plugin_output):
    """List available package upgrades and their versions for each manager."""
    # Build-up a global list of outdated packages per manager.
    outdated_data = {}
    fields = (
        "id",
        "name",
        "installed_version",
        "latest_version",
    )

    for manager in ctx.obj.selected_managers(implements_operation=Operations.outdated):
        packages = tuple(packages_asdict(manager.outdated, fields))

        outdated_data[manager.id] = {
            "id": manager.id,
            "name": manager.name,
            "packages": packages,
        }

        # Serialize errors at the last minute to gather all we encountered.
        outdated_data[manager.id]["errors"] = list(
            {expt.error for expt in manager.cli_errors},
        )

    # Machine-friendly data rendering.
    if ctx.meta["click_extra.table_format"] == ExtendedTableFormat.JSON:
        print_json(outdated_data)
        ctx.exit()

    # Xbar/SwiftBar-friendly plugin rendering.
    if plugin_output:
        BarPluginRenderer().print(outdated_data)
        ctx.exit()

    # Human-friendly content rendering.
    table = []
    for manager_id, outdated_pkg in outdated_data.items():
        for info in outdated_pkg["packages"]:
            installed_version, latest_version = colored_diff(
                info["installed_version"] if info["installed_version"] else "?",
                info["latest_version"],
            )
            table.append(
                (
                    info["id"],
                    info["name"],
                    manager_id,
                    installed_version,
                    latest_version,
                ),
            )

    # Sort and print table.
    ctx.find_root().print_table(
        (
            ("Package ID", SortableField.PACKAGE_ID),
            ("Name", SortableField.PACKAGE_NAME),
            ("Manager", SortableField.MANAGER_ID),
            ("Installed version", SortableField.VERSION),
            ("Latest version", None),
        ),
        table,
        ctx.obj.sort_by,
    )

    if ctx.obj.stats:
        print_stats(Counter({k: len(v["packages"]) for k, v in outdated_data.items()}))


# TODO: make it a --search-strategy=[exact, fuzzy, extended]
# Add details helps => exact: is case-sensitive, and keep all non-alnum chars
# fuzzy: query is case-insensitive, stripped-out of non-alnum chars and
# tokenized (no order sensitive)
# extended, same as fuzzy, but do not limit search to package ID and name.
# extended to description and other metadata depending on manager support.
# Modes:
#  1. strict (--exact, on ID or name)
#  2. substring (regex, no case, no split)
#  3. fuzzy (token-based)
#  4. extended (fuzzy + metadata)
@mpm.command(short_help="Search packages.", section=EXPLORE)
@option(
    "--extended/--id-name-only",
    default=False,
    help="Extend search to description, instead of restricting it to package ID and "
    "name. Implies --description.",
)
@option(
    "--exact/--fuzzy",
    default=False,
    help="Only returns exact matches on package ID or name.",
)
@option(
    "--refilter/--no-refilter",
    default=True,
    help="Let mpm refilters managers' search results.",
)
@argument("query", type=STRING, required=True)
@pass_context
def search(ctx, extended, exact, refilter, query):
    """Search each manager for a package ID, name or description matching the query."""
    # --extended implies --description.
    show_description = ctx.obj.description
    if extended and not ctx.obj.description:
        logging.info("--extended option forces --description option.")
        show_description = True

    # Build-up a global list of package matches per manager.
    matches = {}
    fields = (
        "id",
        "name",
        "latest_version",
        "description",
    )

    search_method = "refiltered_search" if refilter else "search"
    for manager in ctx.obj.selected_managers(implements_operation=Operations.search):
        packages = tuple(
            packages_asdict(
                getattr(manager, search_method)(query, extended, exact),
                fields,
            ),
        )

        matches[manager.id] = {
            "id": manager.id,
            "name": manager.name,
            "packages": packages,
        }

        # Serialize errors at the last minute to gather all we encountered.
        matches[manager.id]["errors"] = list(
            {expt.error for expt in manager.cli_errors},
        )

    # Machine-friendly data rendering.
    if ctx.meta["click_extra.table_format"] == ExtendedTableFormat.JSON:
        print_json(matches)
        ctx.exit()

    # Prepare highlighting helpers.
    query_parts = {query}.union(PackageManager.query_parts(query))
    highlight_query = cached(LRI(max_size=1000))(
        partial(
            highlight,
            patterns=query_parts,
            styling_func=theme.search,
            ignore_case=True,
        ),
    )

    # Human-friendly content rendering.
    table = []
    for manager_id, matching_pkg in matches.items():
        for pkg in matching_pkg["packages"]:
            line = [
                highlight_query(pkg["id"]) if pkg["id"] else "",
                highlight_query(pkg["name"]) if pkg["name"] else "",
                manager_id,
                pkg["latest_version"] if pkg["latest_version"] else "?",
            ]
            if show_description:
                line.append(
                    highlight_query(pkg.get("description"))
                    if pkg.get("description")
                    else "",
                )
            table.append(line)

    # Sort and print table.
    headers = [
        ("Package ID", SortableField.PACKAGE_ID),
        ("Name", SortableField.PACKAGE_NAME),
        ("Manager", SortableField.MANAGER_ID),
        ("Latest version", SortableField.VERSION),
    ]
    if show_description:
        headers.append(("Description", None))
    ctx.find_root().print_table(headers, table, ctx.obj.sort_by)

    if ctx.obj.stats:
        print_stats(Counter({k: len(v["packages"]) for k, v in matches.items()}))


@mpm.command(aliases=["locate"], short_help="Locate CLIs on system.", section=EXPLORE)
@argument("cli_names", type=STRING, nargs=-1, required=True)
@pass_context
def which(ctx, cli_names):
    """Search from the user's environment all CLIs matching the query.

    This is mpm's own version of the `which -a` UNIX command, used internally to locate
    binaries for each manager. It is exposed as a subcommand for convenience and to help
    troubleshoot CLI resolution logic.

    Compared to the venerable `which` command, this will respect the additional path
    configured for each package manager. It will ignore files that are empty (0 size).
    On Windows, it additionally suppress the default lookup in the current directory,
    which takes precedence on other paths.
    """
    if ctx.obj.sort_by:
        logging.warning("Ignore --sort-by option for which command.")

    # Machine-friendly data rendering.
    if ctx.meta["click_extra.table_format"] == ExtendedTableFormat.JSON:
        cli_data = []
        for manager in ctx.obj.selected_managers():
            cli_data.append(
                {
                    "manager_id": manager.id,
                    "cli_paths": list(manager.search_all_cli(cli_names)),
                },
            )
        print_json(cli_data)
        ctx.exit()

    # Print table.
    table = []
    for manager in ctx.obj.selected_managers():
        for priority, found_cli in enumerate(manager.search_all_cli(cli_names)):
            # Resolve symlinks and highlight the CLI name.
            symlink = ""
            if found_cli.is_symlink():
                symlink = "→ " + highlight_cli_name(found_cli.resolve(), cli_names)
            table.append(
                (
                    manager.id,
                    str(priority),
                    highlight_cli_name(found_cli, cli_names),
                    symlink,
                ),
            )
    ctx.find_root().print_table(
        (
            ("Manager ID", SortableField.MANAGER_ID),
            ("Priority", None),
            ("CLI path", None),
            ("Symlink destination", None),
        ),
        table,
        ctx.obj.sort_by,
    )


@mpm.command(short_help="Install a package.", section=MAINTENANCE)
@argument(
    "packages_specs",
    type=STRING,
    nargs=-1,
    required=True,
    help="A mix of plain <package_id>, simple <package_id@version> specifiers or full "
    "<pkg:npm/left-pad> purls.",
)
# TODO: add a --force/--reinstall flag
@pass_context
def install(ctx, packages_specs):
    """Install one or more packages.

    This subcommand is sensible to the order of the package managers selected by the
    user.

    Installation will first proceed for all the packages found to be tied to a specific
    manager. Which is the case for packages provided with precise package specifiers
    (like purl). This will also happens in situations in which a tighter selection of
    managers is provided by the user.

    For packages whose manager is not known, or if multiple managers are candidates for
    the installation, mpm will try to find the best manager to install it with.

    Installation will be attempted with each manager, in the order they were selected.
    If a search for the package ID returns no result from the highest-priority manager,
    we will skip the installation and try the next available managers in the order of
    their priority.
    """
    # Cast generator to tuple because of reuse.
    selected_managers = tuple(
        ctx.obj.selected_managers(implements_operation=Operations.install),
    )
    manager_ids = tuple(manager.id for manager in selected_managers)
    logging.info(
        "Installation priority: > "
        f"{' > '.join(map(theme.invoked_command, manager_ids))}",
    )

    solver = Solver(packages_specs, manager_priority=manager_ids)
    packages_per_managers = solver.resolve_specs_group_by_managers()

    # Install all packages deterministiccaly tied to a specific manager.
    for manager_id, package_specs in packages_per_managers.items():
        if not manager_id:
            continue
        for spec in package_specs:
            try:
                logging.info(
                    f"Install {spec} package with "
                    f"{theme.invoked_command(manager_id)}...",
                )
                manager = pool.get(manager_id)
                output = manager.install(spec.package_id, version=spec.version)
            except NotImplementedError:
                logging.warning(
                    f"{theme.invoked_command(manager_id)} "
                    "does not implement install operation.",
                )
                continue
            echo(output)

    unmatched_packages = packages_per_managers.get(None, [])
    for spec in unmatched_packages:
        for manager in selected_managers:
            logging.info(
                f"Try to install {spec} with {theme.invoked_command(manager.id)}.",
            )

            # Is the package available on this manager?
            matches = None
            try:
                matches = tuple(
                    manager.refiltered_search(
                        extended=False,
                        exact=True,
                        query=spec.package_id,
                    ),
                )
            except NotImplementedError:
                logging.warning(
                    f"{theme.invoked_command(manager.id)} "
                    "does not implement search operation.",
                )
                logging.info(
                    f"{spec.package_id} existence unconfirmed, "
                    "try to directly install it...",
                )
            else:
                if not matches:
                    logging.warning(
                        f"No {spec.package_id} package found "
                        f"on {theme.invoked_command(manager.id)}.",
                    )
                    continue
                # Prevents any incomplete or bad implementation of exact search.
                if len(matches) != 1:
                    msg = "Exact search returned multiple packages."
                    raise ValueError(msg)

            # Allow install subcommand to fail to have the opportunity to catch the
            # CLIError exception and print a comprehensive message.
            with patch.object(manager, "stop_on_error", True):
                try:
                    logging.info(
                        f"Install {spec} package "
                        f"with {theme.invoked_command(manager.id)}...",
                    )
                    output = manager.install(spec.package_id, version=spec.version)
                except NotImplementedError:
                    logging.warning(
                        f"{theme.invoked_command(manager.id)} "
                        "does not implement install operation.",
                    )
                    continue
                except CLIError:
                    logging.warning(
                        f"Could not install {spec} "
                        f"with {theme.invoked_command(manager.id)}.",
                    )
                    continue

            echo(output)
            ctx.exit()


@mpm.command(aliases=["update"], short_help="Upgrade packages.", section=MAINTENANCE)
@option(
    "-A",
    "--all",
    is_flag=True,
    default=False,
    help="Upgrade all outdated packages. "
    "Will make the command ignore package IDs provided as parameters.",
)
@argument(
    "packages_specs",
    type=STRING,
    nargs=-1,
    help="A mix of plain <package_id>, simple <package_id@version> specifiers or full "
    "<pkg:npm/left-pad> purls.",
)
@pass_context
def upgrade(ctx, all, packages_specs):
    """Upgrade one or more outdated packages.

    All outdated package will be upgraded by default if no specifiers are provided as
    arguments. I.e. assumes -A/--all option if no [PACKAGES_SPECS]....

    Packages recognized by multiple managers will be upgraded with each of them. You can
    fine-tune this behavior with more precise package specifiers (like purl) and/or
    tighter selection of managers.

    Packages unrecognized by any selected manager will be skipped.
    """
    if not all and not packages_specs:
        logging.info("No package provided, assume -A/--all option.")
        all = True

    # Full upgrade.
    if all:
        if packages_specs:
            # Deduplicate and sort specifiers for terseness.
            logging.warning(
                f"Ignore {', '.join(sorted(set(packages_specs)))} specifiers "
                "and proceed to a full upgrade...",
            )
        for manager in ctx.obj.selected_managers(
            implements_operation=Operations.upgrade_all,
        ):
            logging.info(
                "Upgrade all outdated packages "
                f"from {theme.invoked_command(manager.id)}...",
            )
            output = manager.upgrade()
            if output:
                logging.info(output)
        ctx.exit()

    # Cast generator to tuple because of reuse.
    selected_managers = tuple(
        ctx.obj.selected_managers(implements_operation=Operations.upgrade),
    )
    manager_ids = tuple(manager.id for manager in selected_managers)

    # Get the subset of selected managers that are implementing the installed operation,
    # so we can query it and know if a package has been installed with it.
    sourcing_managers = tuple(
        ctx.obj.selected_managers(
            keep=manager_ids,
            implements_operation=Operations.installed,
        ),
    )

    solver = Solver(packages_specs, manager_priority=manager_ids)
    for package_id, spec in solver.resolve_package_specs():
        source_manager_ids = set()
        # Use the manager from the spec.
        if spec.manager_id:
            source_manager_ids.add(spec.manager_id)
        # Package is not bound to a manager by the user's specifiers.
        else:
            logging.info(
                f"{spec} not tied to a manager. Search all managers recognizing it.",
            )
            # Find all the managers that have the package installed.
            for manager in sourcing_managers:
                if package_id in map(attrgetter("id"), manager.installed):
                    logging.info(
                        f"{package_id} has been installed "
                        f"with {theme.invoked_command(manager.id)}.",
                    )
                    source_manager_ids.add(manager.id)

        if not source_manager_ids:
            logging.error(
                f"{package_id} is not recognized by any of the selected manager. "
                "Skip it.",
            )
            continue

        logging.info(
            f"Upgrade {package_id} "
            f"with {', '.join(map(theme.invoked_command, sorted(source_manager_ids)))}",
        )
        for manager_id in source_manager_ids:
            manager = pool.get(manager_id)
            output = manager.upgrade(package_id, version=spec.version)
            if output:
                logging.info(output)


@mpm.command(aliases=["uninstall"], short_help="Remove a package.", section=MAINTENANCE)
@argument(
    "packages_specs",
    type=STRING,
    nargs=-1,
    required=True,
    help="A mix of plain <package_id>, simple <package_id@version> specifiers or full "
    "<pkg:npm/left-pad> purls.",
)
@pass_context
def remove(ctx, packages_specs):
    """Remove one or more packages.

    Packages recognized by multiple managers will be remove with each of them. You can
    fine-tune this behavior with more precise package specifiers (like purl) and/or
    tighter selection of managers.

    Packages unrecognized by any selected manager will be skipped.
    """
    # Cast generator to tuple because of reuse.
    selected_managers = tuple(
        ctx.obj.selected_managers(implements_operation=Operations.remove),
    )
    manager_ids = tuple(manager.id for manager in selected_managers)

    # Get the subset of selected managers that are implementing the installed operation,
    # so we can query it and know if a package has been installed with it.
    sourcing_managers = tuple(
        ctx.obj.selected_managers(
            keep=manager_ids,
            implements_operation=Operations.installed,
        ),
    )

    solver = Solver(packages_specs, manager_priority=manager_ids)
    for package_id, spec in solver.resolve_package_specs():
        source_manager_ids = set()
        # Use the manager from the spec.
        if spec.manager_id:
            source_manager_ids.add(spec.manager_id)
        # Package is not bound to a manager by the user's specifiers.
        else:
            logging.info(
                f"{spec} not tied to a manager. Search all managers recognizing it.",
            )
            # Find all the managers that have the package installed.
            for manager in sourcing_managers:
                if package_id in map(attrgetter("id"), manager.installed):
                    logging.info(
                        f"{package_id} has been installed "
                        f"with {theme.invoked_command(manager.id)}.",
                    )
                    source_manager_ids.add(manager.id)

        if not source_manager_ids:
            logging.error(
                f"{package_id} is not recognized by any of the selected manager. "
                "Skip it.",
            )
            continue

        logging.info(
            f"Remove {package_id} "
            f"with {', '.join(map(theme.invoked_command, sorted(source_manager_ids)))}",
        )
        for manager_id in source_manager_ids:
            manager = pool.get(manager_id)
            output = manager.remove(package_id)
            if output:
                logging.info(output)


@mpm.command(short_help="Sync local package info.", section=MAINTENANCE)
@pass_context
def sync(ctx):
    """Sync local package metadata and info from external sources."""
    for manager in ctx.obj.selected_managers(implements_operation=Operations.sync):
        logging.info(f"Sync {theme.invoked_command(manager.id)} package info...")
        manager.sync()


@mpm.command(short_help="Cleanup local data.", section=MAINTENANCE)
@pass_context
def cleanup(ctx):
    """Cleanup local data, temporary artifacts and removes orphaned dependencies."""
    for manager in ctx.obj.selected_managers(implements_operation=Operations.cleanup):
        logging.info(f"Cleanup {theme.invoked_command(manager.id)}...")
        manager.cleanup()


@mpm.command(
    aliases=["lock", "freeze", "snapshot"],
    short_help="Save installed packages to a TOML file.",
    section=SNAPSHOTS,
)
@option(
    "--overwrite",
    "--force",
    "--replace",
    is_flag=True,
    default=False,
    help="Allow the provided TOML file to be silently wiped out if it already exists.",
)
@option(
    "--merge",
    is_flag=True,
    default=False,
    help="Read the provided TOML file and update each entry with the version currently "
    "installed on the system. Requires the [TOML_PATH] argument.",
)
@option(
    "--update-version",
    is_flag=True,
    default=False,
    help="Read the provided TOML file and update each existing entry with the version "
    "currently installed on the system. Requires the [TOML_PATH] argument.",
)
@argument(
    "toml_path",
    type=file_path(writable=True, resolve_path=True, allow_dash=True),
    default="-",
)
@pass_context
def backup(ctx, overwrite, merge, update_version, toml_path):
    """Dump the list of installed packages to a TOML file.

    By default the generated TOML content is displayed directly in the console output.
    So `mpm backup` is the same as a call to `mpm backup -`. To have the result written
    in a file on disk, specify the output file like so: `mpm backup packages.toml`.

    Files produced by this subcommand can be safely consumed by `mpm restore`.

    Sections of the TOML file will be named after the manager ID. Sections are ordered in
    the same order as the manager selection priority. Each section will contain a list of
    package IDs and their installed version.
    """
    if is_stdout(toml_path):
        if merge:
            logging.critical(
                "--merge requires the [TOML_PATH] argument to point to a file.",
            )
            ctx.exit(2)
        if update_version:
            logging.critical(
                "--update-version requires the [TOML_PATH] argument to point to a "
                "file.",
            )
            ctx.exit(2)
        if overwrite:
            logging.warning("Ignore the --overwrite/--force/--replace option.")
        logging.info(f"Print installed package list to {sys.stdout.name}")

    else:
        if merge and update_version:
            logging.critical("--merge and --update-version are mutually exclusive.")
            ctx.exit(2)

        if merge:
            logging.info(f"Merge all installed packages into {toml_path}")
        elif update_version:
            logging.info(
                f"Update in-place all versions of installed packages "
                f"found in {toml_path}",
            )
        else:
            logging.info(f"Dump all installed packages into {toml_path}")

        if toml_path.exists():
            if overwrite:
                logging.warning("Target file exist and will be overwritten.")
            else:
                if merge or update_version:
                    logging.warning("Ignore the --overwrite/--force/--replace option.")
                else:
                    logging.critical("Target file exist and will be overwritten.")
                    ctx.exit(2)
        elif merge:
            logging.critical("--merge requires an existing file.")
            ctx.exit(2)
        elif update_version:
            logging.critical("--update-version requires an existing file.")
            ctx.exit(2)

        if toml_path.suffix.lower() != ".toml":
            logging.critical("Target file is not a TOML file.")
            ctx.exit(2)

    installed_data = {}
    fields = (
        "id",
        "installed_version",
    )
    if merge or update_version:
        installed_data = tomllib.loads(toml_path.read_text(encoding="utf-8"))

    # Leave some metadata as comment.
    content = (
        f"# Generated by mpm v{__version__}.\n"
        f"# Timestamp: {datetime.now().isoformat()}.\n\n"
    )
    # Create one section for each manager.
    for manager in ctx.obj.selected_managers(implements_operation=Operations.installed):
        logging.info(f"Dumping packages from {theme.invoked_command(manager.id)}...")

        packages = tuple(packages_asdict(manager.installed, fields))

        for pkg in packages:
            # Only update version in that mode if the package is already referenced
            # into original TOML file.
            if update_version:
                if pkg["id"] in installed_data.get(manager.id, {}):
                    installed_data[manager.id][pkg["id"]] = str(
                        pkg["installed_version"],
                    )
            # Insert installed package in data structure for standard dump and merge
            # mode.
            else:
                installed_data.setdefault(manager.id, {})[pkg["id"]] = str(
                    pkg["installed_version"],
                )

        # Re-sort package list.
        if installed_data.get(manager.id):
            installed_data[manager.id] = dict(
                sorted(
                    installed_data[manager.id].items(),
                    # Case-insensitive lexicographical sort on keys.
                    key=lambda i: (i[0].lower(), i[0]),
                ),
            )

    # Write each section separated by an empty line for readability.
    content += "\n".join(
        (
            tomli_w.dumps({manager_id: packages})
            for manager_id, packages in installed_data.items()
        )
    )

    echo(content, file=prep_path(toml_path))

    if ctx.obj.stats:
        print_stats(Counter({k: len(v) for k, v in installed_data.items()}))


@mpm.command(
    short_help="Install packages referenced in TOML files.",
    section=SNAPSHOTS,
)
@argument("toml_files", type=File("r"), required=True, nargs=-1)
@pass_context
def restore(ctx, toml_files):
    """Read TOML files then install or upgrade each package referenced in them."""
    # TODO: add an artificial order for managers, so that the [cask] section can install
    # mas CLI first then have [mas] section work in one-go. Use-case: my dotfiles.
    for toml_input in toml_files:
        is_stdin = isinstance(toml_input, TextIOWrapper)
        if is_stdin:
            toml_input.reconfigure(encoding="utf-8")
            toml_filepath = toml_input.name
            toml_content = toml_input.read()
        else:
            toml_filepath = Path(toml_input.name).resolve()
            toml_content = toml_filepath.read_text(encoding="utf-8")

        logging.info(f"Load package list from {toml_filepath}")
        doc = tomllib.loads(toml_content)

        # List unrecognized sections.
        ignored_sections = [
            f"[{section}]" for section in doc if section not in pool.all_manager_ids
        ]
        if ignored_sections:
            plural = "s" if len(ignored_sections) > 1 else ""
            sections = ", ".join(ignored_sections)
            logging.info(f"Ignore {sections} section{plural}.")

        for manager in ctx.obj.selected_managers(
            implements_operation=Operations.install,
        ):
            if manager.id not in doc:
                logging.warning(
                    f"No [{theme.invoked_command(manager.id)}] section found.",
                )
                continue
            logging.info(f"Restore {theme.invoked_command(manager.id)} packages...")
            for package_id, version in doc[manager.id].items():
                spec = Specifier(
                    raw_spec=f"pkg:{manager.id}:/{package_id}{VERSION_SEP}{package_id}",
                    package_id=package_id,
                    manager_id=manager.id,
                    version=version,
                )
                logging.info(f"Install {spec}...")
                output = manager.install(spec.package_id, version=spec.version)
                echo(output)


@mpm.command(
    short_help="Export installed packages to a SBOM document.",
    section=SBOM_SECTION,
)
@option(
    "--spdx/--cyclonedx",
    default=True,
    help="SBOM standard to export to.",
)
@option(
    "--format",
    "export_format",
    type=EnumChoice(ExportFormat),
    help=f"File format of the export. Defaults to JSON for {sys.stdout.name}. If not "
    "provided, will be autodetected from file extension.",
)
@option(
    "--overwrite",
    "--force",
    "--replace",
    is_flag=True,
    default=False,
    help="Allow the target file to be silently wiped out if it already exists.",
)
@argument(
    "export_path",
    type=file_path(writable=True, resolve_path=True, allow_dash=True),
    default="-",
)
@pass_context
def sbom(ctx, spdx, export_format, overwrite, export_path):
    """Export list of installed packages to a SPDX or CycloneDX file."""
    standard = "SPDX" if spdx else "CycloneDX"

    if is_stdout(export_path):
        if overwrite:
            logging.warning("Ignore the --overwrite/--force/--replace option.")
        logging.info(f"Print {standard} export to {sys.stdout.name}")

    else:
        logging.info(f"Export installed packages in {standard} to {export_path}")
        if export_path.exists():
            msg = "Target file exist and will be overwritten."
            if overwrite:
                logging.warning(msg)
            else:
                logging.critical(msg)
                ctx.exit(2)

    # <stdout> format defaults to JSON.
    if is_stdout(export_path):
        if not export_format:
            export_format = ExportFormat.JSON
    # If no export format has been provided, guess it from file name.
    else:
        guessed_format = SBOM.autodetect_export_format(export_path)
        if not export_format:
            export_format = guessed_format
        else:
            if export_format != guessed_format:
                logging.critical(
                    f"Selected {export_format} does not match file extension."
                )
                ctx.exit(2)

    if spdx:
        sbom_class = SPDX
    else:
        if export_format not in (ExportFormat.JSON, ExportFormat.XML):
            logging.critical(f"{standard} does not support {export_format} format.")
            ctx.exit(2)
        sbom_class = CycloneDX

    sbom = sbom_class(export_format)
    sbom.init_doc()

    for manager in ctx.obj.selected_managers(implements_operation=Operations.installed):
        logging.info(f"Export packages from {theme.invoked_command(manager.id)}...")
        for package in manager.installed:
            sbom.add_package(manager, package)

    echo(sbom.export(), file=prep_path(export_path))
