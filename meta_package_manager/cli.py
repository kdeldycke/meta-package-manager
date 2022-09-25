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

from __future__ import annotations

import logging
import sys
from collections import Counter, namedtuple
from contextlib import contextmanager
from datetime import datetime
from functools import partial
from io import TextIOWrapper
from operator import attrgetter
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

import tomli_w
from boltons.cacheutils import LRI, cached
from click_extra import STRING, Choice, File
from click_extra import Path as ClickPath
from click_extra import argument, echo, group, option, option_group, pass_context
from click_extra.colorize import KO, OK, highlight, theme
from click_extra.platform import os_label
from click_extra.tabulate import table_format_option
from cloup import Option

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from cloup import Section

from . import __version__, bar_plugin, logger
from .base import CLIError, Operations, PackageManager, packages_asdict
from .output import (
    SORTABLE_FIELDS,
    BarPluginRenderer,
    TabularOutputFormatter,
    colored_diff,
    print_json,
    print_stats,
    print_table,
)
from .pool import pool

# Subcommand sections.
EXPLORE = Section("Explore subcommands")
MAINTENANCE = Section("Maintenance subcommands")
SNAPSHOTS = Section("Package snapshots subcommands")


XKCD_MANAGER_ORDER = ("pip", "brew", "npm", "dnf", "apt", "steamcmd")
"""Sequence of package managers as defined by `XKCD #1654: Universal Install Script <https://xkcd.com/1654/>`_.

See the corresponding :issue:`implementation rationale in issue #10 <10>`.
"""


def add_manager_to_selection(ctx, param, selected):
    """Store singular manager flag selection in the context."""
    if selected:
        if ctx.obj is None:
            ctx.obj = {"single_manager_selector": []}
        # Parameter's name is transformed into a Python identifier on instantiation.
        # Reverse the process to get our value.
        # Example: "--apt-mint" => "apt_mint" => "apt-mint"
        manager_id = param.name.replace("_", "-")
        ctx.obj["single_manager_selector"].append(manager_id)


def single_manager_selectors() -> Iterator[Option]:
    """Dynamiccaly creates a dedicated flag selector alias for each manager."""
    for manager_id in pool.all_manager_ids:
        yield option(
            f"--{manager_id}",
            is_flag=True,
            default=False,
            help=f"Alias to --manager {manager_id}.",
            expose_value=False,
            callback=add_manager_to_selection,
        )


def bar_plugin_path(ctx, param, value):
    """Print the location of the :doc:`Xbar/SwiftBar plugin <bar-plugin>`.

    Returns the normalized path of the `meta_package_manager.7h.py <https://github.com/kdeldycke/meta-package-manager/meta_package_manager/bar_plugin/meta_package_manager.7h.py>`_ file that is distributed with this Python module. This
    is made available under the :option:`mpm --bar-plugin-path` option:

    .. code-block:: shell-session

        $ mpm --bar-plugin-path
        ~/Library/Python/3.9/lib/python/site-packages/meta_package_manager/bar_plugin/meta_package_manager.7h.py

    This is handy for deployment and initial configuration of Xbar/SwiftBar. I personnly use this in `my dotfiles <https://github.com/kdeldycke/dotfiles>`_.

    Notice that the fully-qualified home directory get rplaces by its shorthand (``~``) if applicable:

    - the full ``/home/user/.python/site-packages/mpm/meta_package_manager.7h.py`` path is simplified as  ``~/.python/site-packages/mpm/meta_package_manager.7h.py``,
    - while ``/usr/bin/python3.9/mpm/bar_plugin/mpm.7h.py`` is returned as-is.
    """
    if value:
        bar_path = Path(bar_plugin.__file__).expanduser().resolve()
        home_dir = Path.home()
        if bar_path.is_relative_to(home_dir):
            home_shorthand = Path("~")
            shorten_bar_path = home_shorthand / bar_path.relative_to(home_dir)
            assert shorten_bar_path.expanduser().resolve() == bar_path
            bar_path = shorten_bar_path
        echo(bar_path)
        ctx.exit()


@group(version=__version__)
@option_group(
    "Package manager selection options",
    option(
        "-m",
        "--manager",
        type=Choice(pool.all_manager_ids, case_sensitive=False),
        multiple=True,
        help="Restrict subcommand to a subset of managers. Repeat to "
        "select multiple managers. The order in which options are provided defines the "
        "order in which subcommands will process them.",
    ),
    option(
        "-e",
        "--exclude",
        type=Choice(pool.all_manager_ids, case_sensitive=False),
        multiple=True,
        help="Exclude a manager. Repeat to exclude multiple managers.",
    ),
    option(
        "-a",
        "--all-managers",
        is_flag=True,
        default=False,
        help="Force evaluation of all manager recognized by mpm, even those "
        "not supported by the current platform. Still applies filtering by --manager "
        "and --exclude options before calling the subcommand.",
    ),
    option(
        "-x",
        "--xkcd",
        is_flag=True,
        default=False,
        help="Preset manager selection as defined by XKCD #1654. Equivalent to: "
        "{}.".format(" ".join(f"--{mid}" for mid in XKCD_MANAGER_ORDER)),
    ),
    *single_manager_selectors(),
)
@option_group(
    "Manager's options",
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
)
@option_group(
    "Output options",
    table_format_option(
        "-o",
        "--output-format",
        type=Choice(
            sorted(TabularOutputFormatter._output_formats), case_sensitive=False
        ),
        help="Rendering mode of the output.",
    ),
    option(
        "--description",
        is_flag=True,
        default=False,
        help="Show package description in results.",
    ),
    option(
        "-s",
        "--sort-by",
        type=Choice(sorted(SORTABLE_FIELDS), case_sensitive=False),
        default="manager_id",
        help="Sort results.",
    ),
    # option('--sort-asc/--sort-desc', default=True)
    option(
        "--stats/--no-stats",
        default=True,
        help="Print per-manager package statistics.",
    ),
)
@option(
    "--bar-plugin-path",
    is_flag=True,
    default=False,
    expose_value=False,
    is_eager=True,
    callback=bar_plugin_path,
    help="Print location of the Xbar/SwiftBar plugin.",
)
@pass_context
def mpm(
    ctx,
    manager,
    exclude,
    all_managers,
    xkcd,
    ignore_auto_updates,
    stop_on_error,
    dry_run,
    description,
    sort_by,
    stats,
):
    """Common CLI options and behavior for managers."""

    # Update the list of selected managers with single selectors.
    if ctx.obj:
        manager = list(manager) + ctx.obj.get("single_manager_selector", [])

    # Silence all log message for JSON rendering unless in debug mode.
    level = logger.level
    level_name = logging._levelToName.get(level, level)
    if ctx.find_root().table_formatter.format_name == "json" and level_name != "DEBUG":
        logger.setLevel(logging.CRITICAL * 2)

    # Select the subset of manager to target, and apply manager-level options.
    selected_managers = partial(
        pool.select_managers,
        keep=manager if not xkcd else XKCD_MANAGER_ORDER,
        drop=exclude,
        keep_unsupported=all_managers,
        # Should we include auto-update packages or not?
        ignore_auto_updates=ignore_auto_updates,
        # Does the manager should raise on error or not.
        stop_on_error=stop_on_error,
        dry_run=dry_run,
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
    short_help="List supported package managers and their location.", section=EXPLORE
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
    if ctx.find_root().table_formatter.format_name == "json":
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
                {expt.error for expt in manager.cli_errors}
            )

        print_json(manager_data)
        ctx.exit()

    # Human-friendly content rendering.
    table = []
    for manager in ctx.obj.selected_managers(**select_params):

        # Build up the OS column content.
        os_infos = OK if manager.supported else KO
        if not manager.supported:
            os_infos += " {} only".format(
                ", ".join(sorted(os_label(os_id) for os_id in manager.platforms))
            )

        # Build up the CLI path column content.
        cli_infos = "{} {}".format(
            OK if manager.cli_path else KO,
            manager.cli_path
            if manager.cli_path
            else f"{', '.join(manager.cli_names)} not found",
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
            )
        )

    print_table(
        (
            ("Manager ID", "manager_id"),
            ("Name", "manager_name"),
            ("Supported", None),
            ("CLI", None),
            ("Executable", None),
            ("Version", "version"),
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
            {expt.error for expt in manager.cli_errors}
        )

    # Filters out non-duplicate packages.
    if duplicates:
        # Re-group packages by their IDs.
        package_sources = {}
        for manager_id, installed_pkg in installed_data.items():
            for package in installed_pkg["packages"]:
                package_sources.setdefault(package["id"], set()).add(manager_id)
        logger.debug(f"Managers sourcing each package: {package_sources}")

        # Identify package IDs shared by multiple managers.
        duplicates_ids = {
            pid for pid, managers in package_sources.items() if len(managers) > 1
        }
        logger.debug(f"Duplicates: {duplicates_ids}")

        # Remove non-duplicates from results.
        for manager_id in installed_data.keys():
            duplicate_packages = tuple(
                p
                for p in installed_data[manager_id]["packages"]
                if p["id"] in duplicates_ids
            )
            installed_data[manager_id]["packages"] = duplicate_packages

    # Machine-friendly data rendering.
    if ctx.find_root().table_formatter.format_name == "json":
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
        logger.info("Force table sorting on package ID because of --duplicates option.")
        sort_by = "package_id"

    # Print table.
    print_table(
        (
            ("Package ID", "package_id"),
            ("Name", "package_name"),
            ("Manager", "manager_id"),
            ("Installed version", "version"),
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
    fields = [
        "id",
        "name",
        "installed_version",
        "latest_version",
    ]
    if plugin_output:
        fields.extend(["label", "upgrade_cli"])

    for manager in ctx.obj.selected_managers(implements_operation=Operations.outdated):

        packages = tuple(packages_asdict(manager.outdated, tuple(fields)))

        # Re-render upgrade CLI for plugin consumption.
        if plugin_output:
            for info in packages:
                info["upgrade_cli"] = BarPluginRenderer.render_cli(
                    info["upgrade_cli"], plugin_format=plugin_output
                )

        outdated_data[manager.id] = {
            "id": manager.id,
            "name": manager.name,
            "packages": packages,
        }

        # Only include full-upgrade CLI for plugin.
        if plugin_output and packages:
            try:
                upgrade_all_cli = manager.upgrade_all_cli()
            except NotImplementedError:
                # Fallback on mpm itself which is capable of simulating a full upgrade.
                logger.warning(f"{manager.id} does not implement upgrade_all_cli.")
                mpm_exec = bar_plugin.MPMPlugin().mpm_exec
                upgrade_all_cli = (*mpm_exec, f"--{manager.id}", "upgrade", "--all")
                logger.debug(f"Fallback to direct mpm call: {upgrade_all_cli}")
            outdated_data[manager.id]["upgrade_all_cli"] = BarPluginRenderer.render_cli(
                upgrade_all_cli, plugin_format=plugin_output
            )

        # Serialize errors at the last minute to gather all we encountered.
        outdated_data[manager.id]["errors"] = list(
            {expt.error for expt in manager.cli_errors}
        )

    # Machine-friendly data rendering.
    if ctx.find_root().table_formatter.format_name == "json":
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
                )
            )

    # Sort and print table.
    print_table(
        (
            ("Package ID", "package_id"),
            ("Name", "package_name"),
            ("Manager", "manager_id"),
            ("Installed version", "version"),
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
    help="Extend search to description, instead of restricting it to package ID and name. Implies --description.",
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
        logger.warning("--extended option forces --description option.")
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
                getattr(manager, search_method)(query, extended, exact), fields
            )
        )

        matches[manager.id] = {
            "id": manager.id,
            "name": manager.name,
            "packages": packages,
        }

        # Serialize errors at the last minute to gather all we encountered.
        matches[manager.id]["errors"] = list(
            {expt.error for expt in manager.cli_errors}
        )

    # Machine-friendly data rendering.
    if ctx.find_root().table_formatter.format_name == "json":
        print_json(matches)
        ctx.exit()

    # Prepare highlighting helpers.
    query_parts = {query}.union(PackageManager.query_parts(query))
    highlight_query = cached(LRI(max_size=1000))(
        partial(
            highlight,
            substrings=query_parts,
            styling_method=theme.search,
            ignore_case=True,
        )
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
                    else ""
                )
            table.append(line)

    # Sort and print table.
    headers = [
        ("Package ID", "package_id"),
        ("Name", "package_name"),
        ("Manager", "manager_id"),
        ("Latest version", "version"),
    ]
    if show_description:
        headers.append(("Description", "description"))
    print_table(headers, table, ctx.obj.sort_by)

    if ctx.obj.stats:
        print_stats(Counter({k: len(v["packages"]) for k, v in matches.items()}))


@mpm.command(short_help="Install a package.", section=MAINTENANCE)
@argument("package_id", type=STRING, required=True)
# TODO: add a --force/--reinstall flag
@pass_context
def install(ctx, package_id):
    """Install the provided package ID using one of the selected manager."""
    # Cast generator to tuple because of reuse.
    selected_managers = tuple(
        ctx.obj.selected_managers(implements_operation=Operations.install)
    )

    logger.info(
        f"Package manager order: {', '.join([m.id for m in selected_managers])}"
    )

    for manager in selected_managers:
        logger.debug(f"Try to install {package_id} with {manager.id}.")

        # Is the package available on this manager?
        matches = None
        try:
            matches = tuple(
                manager.refiltered_search(extended=False, exact=True, query=package_id)
            )
        except NotImplementedError:
            logger.warning(f"{manager.id} does not implement search operation.")
            logger.info(
                f"{package_id} existence unconfirmed, try to directly install it..."
            )
        else:
            if not matches:
                logger.warning(f"No {package_id} package found on {manager.id}.")
                continue
            # Prevents any incomplete or bad implementation of exact search.
            if len(matches) != 1:
                raise ValueError("Exact search returned multiple packages.")

        # Allow install subcommand to fail to have the opportunity to catch the CLIError exception and print
        # a comprehensive message.
        with patch.object(manager, "stop_on_error", True):
            try:
                logger.info(f"Install {package_id} package from {manager.id}...")
                output = manager.install(package_id)
            except NotImplementedError:
                logger.warning(f"{manager.id} does not implement install operation.")
                continue
            except CLIError:
                logger.warning(f"Could not install {package_id} with {manager.id}.")
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
@argument("package_ids", type=STRING, nargs=-1)
@pass_context
def upgrade(ctx, all, package_ids):
    """Upgrade one or more outdated packages.

    Defaults to upgrading all outdated package if none provided as arguments (i.e. assumes
    -A/--all if no [PACKAGE_IDS]).

    Upgrade will only proceed if no ambiguity is uncovered. Packages recognized by multiple
    managers will be skipped. You can remove that ambiguity by carefully specifying the subset of
    managers to consider for upgrade.

    Unknown packages will be skipped.
    """
    if not all and not package_ids:
        logger.warning("No package provided, assume -A/--all option.")
        all = True

    # Deduplicate entries.
    package_ids = set(package_ids)

    # Full upgrade.
    if all:
        if package_ids:
            logger.debug(
                f"Ignore provided {', '.join(sorted(package_ids))} packages and proceed to a full upgrade..."
            )
        for manager in ctx.obj.selected_managers(
            implements_operation=Operations.upgrade_all
        ):
            logger.info(f"Upgrade all outdated packages from {manager.id}...")
            output = manager.upgrade()
            if output:
                logger.info(output)
        ctx.exit()

    # Specific list of package to upgrade has been requested. We need to
    # validate them before proceeding.

    # For each package, we list the managers they were sourced from.
    package_sources = {}
    for manager in ctx.obj.selected_managers(implements_operation=Operations.upgrade):
        for package in manager.installed:
            if package.id in package_ids:
                package_sources.setdefault(package.id, set()).add(manager.id)
    logger.debug(f"Managers sourcing each package: {package_sources}")

    for package_id in package_ids:

        # Skip unrecognized packages.
        if package_id not in package_sources:
            logger.error(
                f"{package_id} is not recognized by any of the selected manager."
                f" Skip its upgrade."
            )
            continue

        # A package to upgrade that was sourced from multiple managers leads to undefined
        # behavior. What should we do in this case? Upgrade the package with each manager? Only the first one? A random one?
        # We choose to play it safe and simply report this ambiguous situation to
        # the user and skip the package.
        managers = package_sources[package_id]
        if len(managers) > 1:
            logger.error(
                f"{package_id} was sourced from multiple managers: {', '.join(sorted(managers))}."
                " Skip its upgrade."
            )
            continue

        assert len(managers) == 1
        manager_id = managers.pop()
        manager = pool.get(manager_id)
        logger.info(f"Proceed to upgrade {package_id} with {manager_id}...")
        output = manager.upgrade(package_id)
        if output:
            logger.info(output)


@mpm.command(aliases=["uninstall"], short_help="Remove a package.", section=MAINTENANCE)
@argument("package_id", type=STRING, required=True)
@pass_context
def remove(ctx, package_id):
    """Remove the provided package using one of the selected manager."""
    # Cast generator to tuple because of reuse.
    selected_managers = tuple(
        ctx.obj.selected_managers(implements_operation=Operations.remove)
    )

    logger.info(
        f"Package manager order: {', '.join([m.id for m in selected_managers])}"
    )

    for manager in selected_managers:
        logger.debug(f"Try to remove {package_id} with {manager.id}.")

        # Is the package installed with this manager?
        installed = set()
        try:
            installed = map(attrgetter("id"), manager.installed)
        except NotImplementedError:
            logger.warning(f"{manager.id} does not implement installed operation.")
            logger.info(
                f"{package_id} existence unconfirmed, try to directly remove it..."
            )
        else:
            match = package_id in installed
            if not match:
                logger.warning(f"{package_id} was not installed by {manager.id}.")
                continue
            logger.info(f"{package_id} has been installed by {manager.id}.")

        # Allow remove subcommand to fail to have the opportunity to catch the CLIError exception and print
        # a comprehensive message.
        with patch.object(manager, "stop_on_error", True):
            try:
                logger.info(f"Remove {package_id} package with {manager.id}...")
                output = manager.remove(package_id)
            except NotImplementedError:
                logger.warning(f"{manager.id} does not implement remove operation.")
                continue
            except CLIError:
                logger.warning(f"Could not remove {package_id} with {manager.id}.")
                continue

        echo(output)
        ctx.exit()


@mpm.command(short_help="Sync local package info.", section=MAINTENANCE)
@pass_context
def sync(ctx):
    """Sync local package metadata and info from external sources."""
    for manager in ctx.obj.selected_managers(implements_operation=Operations.sync):
        logger.info(f"Sync {manager.id} package info...")
        manager.sync()


@mpm.command(short_help="Cleanup local data.", section=MAINTENANCE)
@pass_context
def cleanup(ctx):
    """Cleanup local data, temporary artifacts and removes orphaned dependencies."""
    for manager in ctx.obj.selected_managers(implements_operation=Operations.cleanup):
        logger.info(f"Cleanup {manager.id}...")
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
    help="Read the provided TOML file and update each entry with the version currently installed on the system. Requires the [TOML_PATH] argument.",
)
@option(
    "--update-version",
    is_flag=True,
    default=False,
    help="Read the provided TOML file and update each existing entry with the version currently installed on the system. Requires the [TOML_PATH] argument.",
)
@argument(
    "toml_path",
    type=ClickPath(
        dir_okay=False,
        writable=True,
        resolve_path=True,
        allow_dash=True,
        path_type=Path,
    ),
    default="-",
)
@pass_context
def backup(ctx, overwrite, merge, update_version, toml_path):
    """Dump the list of installed packages to a TOML file.

    By default the generated TOML content is displayed directly in the console
    output. So `mpm backup` is the same as a call to `mpm backup -`. To have
    the result written in a file on disk, specify the output file like so:
    `mpm backup packages.toml`.

    Files produced by this subcommand can be safely consumed by `mpm restore`.
    """

    def is_stdout(filepath):
        return str(filepath) == "-"

    if is_stdout(toml_path):
        if merge:
            logger.fatal(
                "--merge requires the [TOML_PATH] argument to point to a file."
            )
            ctx.exit(2)
        if update_version:
            logger.fatal(
                "--update-version requires the [TOML_PATH] argument to point to a file."
            )
            ctx.exit(2)
        if overwrite:
            logger.warning("Ignore the --overwrite/--force/--replace option.")
        logger.info(f"Print installed package list to {sys.stdout.name}")

    else:
        if merge and update_version:
            logger.fatal("--merge and --update-version are mutually exclusive.")
            ctx.exit(2)

        if merge:
            logger.info(f"Merge all installed packages into {toml_path}")
        elif update_version:
            logger.info(
                f"Update in-place all versions of installed packages found in {toml_path}"
            )
        else:
            logger.info(f"Dump all installed packages into {toml_path}")

        if toml_path.exists():
            if overwrite:
                logger.warning("Target file exist and will be overwritten.")
            else:
                if merge or update_version:
                    logger.warning("Ignore the --overwrite/--force/--replace option.")
                else:
                    logger.fatal("Target file exist and will be overwritten.")
                    ctx.exit(2)
        elif merge:
            logger.fatal("--merge requires an existing file.")
            ctx.exit(2)
        elif update_version:
            logger.fatal("--update-version requires an existing file.")
            ctx.exit(2)

        if toml_path.suffix.lower() != ".toml":
            logger.fatal("Target file is not a TOML file.")
            ctx.exit(2)

    installed_data = {}
    fields = (
        "id",
        "installed_version",
    )
    if merge or update_version:
        installed_data = tomllib.loads(toml_path.read_text())

    @contextmanager
    def file_writer(filepath):
        """A context-aware file writer which default to stdout if no path is
        provided."""
        if is_stdout(filepath):
            yield sys.stdout
        else:
            writer = filepath.open("w")
            yield writer
            writer.close()

    with file_writer(toml_path) as f:

        # Leave some metadata as comment.
        f.write(f"# Generated by mpm v{__version__}.\n")
        f.write(f"# Timestamp: {datetime.now().isoformat()}.\n")

        # Create one section for each manager.
        for manager in ctx.obj.selected_managers(
            implements_operation=Operations.installed
        ):
            logger.info(f"Dumping packages from {manager.id}...")

            packages = tuple(packages_asdict(manager.installed, fields))

            for pkg in packages:
                # Only update version in that mode if the package is already referenced
                # into original TOML file.
                if update_version:
                    if pkg["id"] in installed_data.get(manager.id, {}):
                        installed_data[manager.id][pkg["id"]] = str(
                            pkg["installed_version"]
                        )
                # Insert installed package in data structure for standard dump and merge
                # mode.
                else:
                    installed_data.setdefault(manager.id, {})[pkg["id"]] = str(
                        pkg["installed_version"]
                    )

            # Re-sort package list.
            if installed_data.get(manager.id):
                installed_data[manager.id] = dict(
                    sorted(installed_data[manager.id].items())
                )

        # Write each section separated by an empty line for readability.
        for manager_id, packages in installed_data.items():
            f.write("\n")
            f.write(tomli_w.dumps({manager_id: packages}))

    if ctx.obj.stats:
        print_stats(Counter({k: len(v) for k, v in installed_data.items()}))


@mpm.command(
    short_help="Install packages in batch as specified by TOML files.",
    section=SNAPSHOTS,
)
@argument("toml_files", type=File("r"), required=True, nargs=-1)
@pass_context
def restore(ctx, toml_files):
    """Read TOML files then install or upgrade each package referenced in them.

    Version specified in the TOML file is ignored in the current implementation.
    """
    for toml_input in toml_files:

        is_stdin = isinstance(toml_input, TextIOWrapper)
        toml_filepath = toml_input.name if is_stdin else Path(toml_input.name).resolve()
        logger.info(f"Load package list from {toml_filepath}")

        doc = tomllib.loads(toml_input.read())

        # List unrecognized sections.
        ignored_sections = [
            f"[{section}]" for section in doc if section not in pool.all_manager_ids
        ]
        if ignored_sections:
            plural = "s" if len(ignored_sections) > 1 else ""
            sections = ", ".join(ignored_sections)
            logger.info(f"Ignore {sections} section{plural}.")

        for manager in ctx.obj.selected_managers(
            implements_operation=Operations.install
        ):
            if manager.id not in doc:
                logger.warning(f"No [{manager.id}] section found.")
                continue
            logger.info(f"Restore {manager.id} packages...")
            for package_id, version in doc[manager.id].items():
                # Let the command fail if the manager doesn't implement the
                # install operation.
                logger.info(f"Install {package_id} package from {manager.id}...")
                output = manager.install(package_id)
                echo(output)
