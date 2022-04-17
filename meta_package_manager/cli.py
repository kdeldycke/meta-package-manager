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

import logging
import re
import sys
from collections import namedtuple
from datetime import datetime
from functools import partial
from io import TextIOWrapper
from operator import getitem
from pathlib import Path

import tomli_w
from boltons.cacheutils import LRI, cached
from boltons.strutils import complement_int_list, int_ranges_from_int_list
from click_extra import (
    STRING,
    Choice,
    File,
    argument,
    echo,
    group,
    option,
    option_group,
    pass_context,
)
from click_extra.colorize import KO, OK, theme
from click_extra.platform import os_label
from click_extra.tabulate import table_format_option

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from cloup import Section

from . import __version__, bar_plugin, logger
from .base import CLI_FORMATS, CLIError, PackageManager
from .output import (
    SORTABLE_FIELDS,
    TabularOutputFormatter,
    print_json,
    print_stats,
    print_table,
)
from .pool import pool
from .version import TokenizedString

# Sub-command sections.
EXPLORE = Section("Explore commands")
MAINTENANCE = Section("Maintainance commands")
SNAPSHOTS = Section("Package snapshots commands")


XKCD_MANAGER_ORDER = ("pip", "brew", "npm", "dnf", "apt")


def add_manager_to_selection(ctx, param, selected):
    """Store singular manager flag selection in the context."""
    if selected:
        if ctx.obj is None:
            ctx.obj = {"single_manager_selector": []}
        # Parameter's name is transformed into a Python identifier on instanciation.
        # Reverse the process to get our value.
        # Example: "--apt-mint" => "apt_mint" => "apt-mint"
        manager_id = param.name.replace("_", "-")
        ctx.obj["single_manager_selector"].append(manager_id)


def single_manager_selectors():
    """Dynamiccaly creates a dedicated flag selector for each manager."""
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
    """Print the location of the Xbar/SwiftBar plugin.

    Replaces the fully-qualified home directory by its shorthand if applicable.
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
        help="Restrict sub-command to a subset of package managers. Repeat to "
        "select multiple managers. The order in which options are provided defines the "
        "order in which sub-commands will process them.",
    ),
    option(
        "-e",
        "--exclude",
        type=Choice(pool.all_manager_ids, case_sensitive=False),
        multiple=True,
        help="Exclude a package manager. Repeat to exclude multiple managers.",
    ),
    option(
        "-a",
        "--all-managers",
        is_flag=True,
        default=False,
        help="Force evaluation of all package manager implemented by mpm, even those "
        "not supported by the current platform. Still applies filtering by --manager "
        "and --exclude options before calling the subcommand.",
    ),
    option(
        "-x",
        "--xkcd",
        is_flag=True,
        default=False,
        help="Preset manager selection as defined by XKCD #1654, i.e. "
        "{}.".format(", ".join(map(theme.choice, XKCD_MANAGER_ORDER))),
    ),
    *single_manager_selectors(),
)
@option_group(
    "Manager's options",
    option(
        "--ignore-auto-updates/--include-auto-updates",
        default=True,
        help="Report all outdated packages, including those tagged as "
        "auto-updating. Only applies to 'outdated' and 'upgrade' commands.",
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
    help="Print location of the mpm Xbar/SwiftBar plugin.",
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
    sort_by,
    stats,
):
    """Common CLI options and behavior for multiple package managers."""

    # Update the list of selected managers with single selectors.
    if ctx.obj:
        manager = list(manager) + ctx.obj.get("single_manager_selector", [])

    # Silence all log message for JSON rendering unless in debug mode.
    level = logger.level
    level_name = logging._levelToName.get(level, level)
    if ctx.find_root().table_formatter.format_name == "json" and level_name != "DEBUG":
        logger.setLevel(logging.CRITICAL * 2)

    # Select the subset of manager to target, and apply manager-level options.
    selected_managers = pool.select_managers(
        keep=manager if not xkcd else XKCD_MANAGER_ORDER,
        drop=exclude,
        drop_unsupported=not all_managers,
        # Only keep inactive managers to show them in the "managers" subcommand table.
        # Filters them out in any other subcommand.
        drop_inactive=ctx.invoked_subcommand != "managers",
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
            "sort_by",
            "stats",
        ),
        defaults=(
            selected_managers,
            sort_by,
            stats,
        ),
    )()


@mpm.command(
    short_help="List supported package managers and their location.", section=EXPLORE
)
@pass_context
def managers(ctx):
    """List all supported package managers and their presence on the system."""
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
        for manager in ctx.obj.selected_managers:
            manager_data[manager.id] = {fid: getattr(manager, fid) for fid in fields}
            # Serialize errors at the last minute to gather all we encountered.
            manager_data[manager.id]["errors"] = list(
                {expt.error for expt in manager.cli_errors}
            )

        print_json(manager_data)
        return

    # Human-friendly content rendering.
    table = []
    for manager in ctx.obj.selected_managers:

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
                manager.name,
                getattr(theme, "success" if manager.fresh else "error")(manager.id),
                os_infos,
                cli_infos,
                OK if manager.executable else "",
                version_infos,
            )
        )

    print_table(
        (
            ("Package manager", "manager_name"),
            ("ID", "manager_id"),
            ("Supported", None),
            ("CLI", None),
            ("Executable", None),
            ("Version", "version"),
        ),
        table,
        ctx.obj.sort_by,
    )


@mpm.command(short_help="List installed packages.", section=EXPLORE)
@pass_context
def installed(ctx):
    """List all packages installed on the system from all managers."""
    # Build-up a global dict of installed packages per manager.
    installed_data = {}

    for manager in ctx.obj.selected_managers:
        installed_data[manager.id] = {
            "id": manager.id,
            "name": manager.name,
            "packages": list(manager.installed.values()),
        }

        # Serialize errors at the last minute to gather all we encountered.
        installed_data[manager.id]["errors"] = list(
            {expt.error for expt in manager.cli_errors}
        )

    # Machine-friendly data rendering.
    if ctx.find_root().table_formatter.format_name == "json":
        print_json(installed_data)
        return

    # Human-friendly content rendering.
    table = []
    for manager_id, installed_pkg in installed_data.items():
        table += [
            (
                info["name"],
                info["id"],
                manager_id,
                info["installed_version"] if info["installed_version"] else "?",
            )
            for info in installed_pkg["packages"]
        ]

    # Sort and print table.
    print_table(
        (
            ("Package name", "package_name"),
            ("ID", "package_id"),
            ("Manager", "manager_id"),
            ("Installed version", "version"),
        ),
        table,
        ctx.obj.sort_by,
    )

    if ctx.obj.stats:
        print_stats(installed_data)


@mpm.command(short_help="List outdated packages.", section=EXPLORE)
@option(
    "-c",
    "--cli-format",
    type=Choice(sorted(CLI_FORMATS), case_sensitive=False),
    default="plain",
    help="Format of CLI fields in JSON output.",
)
@pass_context
def outdated(ctx, cli_format):
    """List available package upgrades and their versions for each manager."""
    render_cli = partial(PackageManager.render_cli, cli_format=cli_format)

    # Build-up a global list of outdated packages per manager.
    outdated_data = {}

    for manager in ctx.obj.selected_managers:

        try:
            packages = tuple(map(dict, manager.outdated.values()))
        except NotImplementedError:
            logger.warning(f"{manager.id} does not implement outdated command.")
            continue

        for info in packages:
            info.update({"upgrade_cli": render_cli(manager.upgrade_cli(info["id"]))})

        outdated_data[manager.id] = {
            "id": manager.id,
            "name": manager.name,
            "packages": packages,
        }

        # Do not include the full-upgrade CLI if we did not detect any outdated
        # package.
        if packages:
            try:
                upgrade_all_cli = manager.upgrade_all_cli()
            except NotImplementedError:
                # Fallback on mpm itself which is capable of simulating a full
                # upgrade.
                upgrade_all_cli = ("mpm", "--manager", manager.id, "upgrade")
            outdated_data[manager.id]["upgrade_all_cli"] = render_cli(upgrade_all_cli)

        # Serialize errors at the last minute to gather all we encountered.
        outdated_data[manager.id]["errors"] = list(
            {expt.error for expt in manager.cli_errors}
        )

    # Machine-friendly data rendering.
    if ctx.find_root().table_formatter.format_name == "json":
        print_json(outdated_data)
        return

    # Human-friendly content rendering.
    table = []
    for manager_id, outdated_pkg in outdated_data.items():
        table += [
            (
                info["name"],
                info["id"],
                manager_id,
                info["installed_version"] if info["installed_version"] else "?",
                info["latest_version"],
            )
            for info in outdated_pkg["packages"]
        ]

    # Sort and print table.
    print_table(
        (
            ("Package name", "package_name"),
            ("ID", "package_id"),
            ("Manager", "manager_id"),
            ("Installed version", "version"),
            ("Latest version", None),
        ),
        table,
        ctx.obj.sort_by,
    )

    if ctx.obj.stats:
        print_stats(outdated_data)


# TODO: make it a --search-strategy=[exact, fuzzy, extended]
# Add details helps => exact: is case-sensitive, and keep all non-alnum chars
# fuzzy: query is case-insensitive, stripped-out of non-alnum chars and
# tokenized (no order sensitive)
# extended, same as fuzzy, but do not limit search to package name and ID.
# extended to description and other metadata depending on manager support.
# Modes:
#  1. strict (--exact)
#  2. substring (regex, no case, no split)
#  3. fuzzy (token-based)
#  4. extended (+ metadata)
@mpm.command(short_help="Search packages.", section=EXPLORE)
@option(
    "--extended/--package-name",
    default=False,
    help="Extend search to additional package metadata like description, "
    "instead of restricting it package ID and name.",
)
@option(
    "--exact/--fuzzy",
    default=False,
    help="Only returns exact matches, or enable fuzzy search in substrings.",
)
@argument("query", type=STRING, required=True)
@pass_context
def search(ctx, extended, exact, query):
    """Search packages from all managers."""
    # Build-up a global list of package matches per manager.
    matches = {}

    for manager in ctx.obj.selected_managers:

        # Allow managers to not implement search.
        try:
            results = manager.search(query, extended, exact).values()
        except NotImplementedError:
            logger.warning(f"{manager.id} does not implement search command.")
            continue

        matches[manager.id] = {
            "id": manager.id,
            "name": manager.name,
            "packages": list(results),
        }

        # Serialize errors at the last minute to gather all we encountered.
        matches[manager.id]["errors"] = list(
            {expt.error for expt in manager.cli_errors}
        )

    # Machine-friendly data rendering.
    if ctx.find_root().table_formatter.format_name == "json":
        print_json(matches)
        return

    # Prepare highlighting helpers.
    query_parts = {query}.union(map(str, TokenizedString(query)))

    @cached(LRI(max_size=1000))
    def highlight(string):
        # Ranges of character indices flagged for highlighting.
        ranges = set()

        for part in query_parts:
            # Search for occurrences of query parts in original string.
            occurrences = (
                match.start() for match in re.finditer(part, string, re.IGNORECASE)
            )
            # Flag matching substrings for highlighting.
            for match_start in occurrences:
                match_end = match_start + len(part) - 1
                ranges.add(f"{match_start}-{match_end}")

        # Reduce index ranges, compute complement ranges, transform them to
        # list of integers.
        ranges = ",".join(ranges)
        bold_ranges = int_ranges_from_int_list(ranges)
        normal_ranges = int_ranges_from_int_list(
            complement_int_list(ranges, range_end=len(string))
        )

        # Apply style to range of characters flagged as matching.
        styled_str = ""
        for i, j in sorted(bold_ranges + normal_ranges):
            segment = getitem(string, slice(i, j + 1))
            if (i, j) in bold_ranges:
                segment = theme.search(segment)
            styled_str += segment

        return styled_str

    # Human-friendly content rendering.
    table = []
    for manager_id, matching_pkg in matches.items():
        table += [
            (
                highlight(info["name"]),
                highlight(info["id"]),
                manager_id,
                info["latest_version"] if info["latest_version"] else "?",
            )
            for info in matching_pkg["packages"]
        ]

    # Sort and print table.
    print_table(
        (
            ("Package name", "package_name"),
            ("ID", "package_id"),
            ("Manager", "manager_id"),
            ("Latest version", "version"),
        ),
        table,
        ctx.obj.sort_by,
    )

    if ctx.obj.stats:
        print_stats(matches)


@mpm.command(short_help="Install a package.", section=MAINTENANCE)
@argument("package_id", type=STRING, required=True)
# TODO: add a --force/--reinstall flag
@pass_context
def install(ctx, package_id):
    """Install the provided package using one of the provided package manager."""
    # Cast generator to tuple because of reuse.
    selected_managers = tuple(ctx.obj.selected_managers)

    logger.info(
        f"Package manager order: {', '.join([m.id for m in selected_managers])}"
    )

    for manager in selected_managers:
        logger.debug(f"Try to install {package_id} with {manager.id}.")

        # Is the package available on this manager?
        matches = None
        try:
            matches = manager.search(extended=False, exact=True, query=package_id)
        except NotImplementedError:
            logger.warning(
                f"No way to search for {package_id} with {manager.id}. Try to directly install it."
            )
        else:
            if not matches:
                logger.warning(f"No {package_id} package found on {manager.id}.")
                continue
            assert len(matches) == 1

        # Allow install subcommand to fail.
        default_value = manager.stop_on_error
        manager.stop_on_error = True
        try:
            output = manager.install(package_id)
        except CLIError:
            logger.warning(f"Could not install {package_id} with {manager.id}.")

            # Restore default value.
            manager.stop_on_error = default_value

            continue

        # Restore default value.
        manager.stop_on_error = default_value

        echo(output)
        return


@mpm.command(short_help="Upgrade all packages.", section=MAINTENANCE)
@pass_context
def upgrade(ctx):
    """Perform a full package upgrade on all available managers."""
    for manager in ctx.obj.selected_managers:
        logger.info(f"Updating all outdated packages from {manager.id}...")
        try:
            output = manager.upgrade_all()
        except NotImplementedError:
            logger.warning(f"{manager.id} does not implement upgrade command.")
            continue

        if output:
            logger.info(output)


@mpm.command(short_help="Sync local package info.", section=MAINTENANCE)
@pass_context
def sync(ctx):
    """Sync local package metadata and info from external sources."""
    for manager in ctx.obj.selected_managers:
        manager.sync()


@mpm.command(short_help="Cleanup local data.", section=MAINTENANCE)
@pass_context
def cleanup(ctx):
    """Cleanup local data and temporary artifacts."""
    for manager in ctx.obj.selected_managers:
        manager.cleanup()


@mpm.command(short_help="Save installed packages to a TOML file.", section=SNAPSHOTS)
@argument("toml_output", type=File("w"), default="-")
@pass_context
def backup(ctx, toml_output):
    """Dump the list of installed packages to a TOML file.

    By default the generated TOML content is displayed directly in the console
    output. So `mpm backup` is the same as a call to `mpm backup -`. To have
    the result written in a file on disk, specify the output file like so:
    `mpm backup ./mpm-packages.toml`.

    The TOML file can then be safely consumed by the `mpm restore` command.
    """
    is_stdout = isinstance(toml_output, TextIOWrapper)
    toml_filepath = toml_output.name if is_stdout else Path(toml_output.name).resolve()
    logger.info(f"Backup package list to {toml_filepath}")

    if not is_stdout:
        if toml_filepath.exists() and not toml_filepath.is_file():
            logger.error("Target file exist and is not a file.")
            return
        if toml_filepath.suffix.lower() != ".toml":
            logger.error("Target file is not a TOML file.")
            return

    # Leave some metadata as comment.
    doc = f"# Generated by mpm v{__version__}.\n"
    doc += f"# Timestamp: {datetime.now().isoformat()}.\n"

    installed_data = {}

    # Create one section for each package manager.
    for manager in ctx.obj.selected_managers:
        logger.info(f"Dumping packages from {manager.id}...")
        installed_packages = manager.installed.values()

        # Prepare data for stats.
        installed_data[manager.id] = {
            "id": manager.id,
            "packages": installed_packages,
        }

        pkg_data = dict(
            sorted((p["id"], str(p["installed_version"])) for p in installed_packages)
        )

        if pkg_data:
            doc += "\n" + tomli_w.dumps({manager.id: pkg_data})

    toml_output.write(doc)

    if ctx.obj.stats:
        print_stats(installed_data)


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

        for manager in ctx.obj.selected_managers:
            if manager.id not in doc:
                logger.warning(f"No [{manager.id}] section found.")
                continue
            logger.info(f"Restore {manager.id} packages...")
            for package_id, version in doc[manager.id].items():
                output = manager.install(package_id)
                echo(output)
