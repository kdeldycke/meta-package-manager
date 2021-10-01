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
from datetime import datetime
from functools import partial
from io import TextIOWrapper
from operator import getitem, itemgetter
from pathlib import Path
from time import perf_counter

import click
import click_log
import tomli
import tomli_w
from boltons.cacheutils import LRI, cached
from boltons.strutils import complement_int_list, int_ranges_from_int_list, strip_ansi
from cli_helpers.tabular_output import TabularOutputFormatter
from click_help_colors import version_option
from simplejson import dumps as json_dumps

from . import CLI_NAME, __version__, env_data, logger, reset_logger
from .base import CLI_FORMATS, CLIError, PackageManager
from .config import load_conf
from .managers import ALL_MANAGER_IDS, select_managers
from .platform import os_label
from .version import TokenizedString

# Initialize the table formatter.
table_formatter = TabularOutputFormatter()


# Register all rendering modes for table data.
RENDERING_MODES = {"json"}
RENDERING_MODES.update(table_formatter.supported_formats)
RENDERING_MODES = frozenset(RENDERING_MODES)


# List of fields IDs allowed to be sorted.
SORTABLE_FIELDS = {
    "manager_id",
    "manager_name",
    "package_id",
    "package_name",
    "version",
}


XKCD_MANAGER_ORDER = ("pip", "brew", "npm", "apt")
assert set(ALL_MANAGER_IDS).issuperset(XKCD_MANAGER_ORDER)


# Pre-rendered UI-elements.
OK = click.style("✓", fg="green")
KO = click.style("✘", fg="red")


click_log.basic_config(logger)


def json(data):
    """Utility function to render data structure into pretty printed JSON.

    Also care of internal objects like `TokenizedString` and `Path`:
    """

    def serialize_objects(obj):
        if isinstance(obj, (TokenizedString, Path)):
            return str(obj)
        raise TypeError(repr(obj) + " is not JSON serializable.")

    return json_dumps(
        data,
        sort_keys=True,
        indent=4,
        separators=(",", ": "),
        default=serialize_objects,
    )


def print_table(header_defs, rows, sort_key=None):
    """Utility to print a table and sort its content."""
    # Do not print anything, not even table headers if no rows.
    if not rows:
        return

    header_labels = (label for label, _ in header_defs)

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

    for line in table_formatter.format_output(
        sorted(rows, key=sort_method), header_labels, disable_numparse=True
    ):
        click.echo(line.encode("utf-8"))


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


def timeit():
    """Print elapsed execution time."""
    ctx = click.get_current_context()
    if ctx.obj["time"]:
        start_time = ctx.obj["start_time"]
        click.echo(f"Execution time: {perf_counter() - start_time:0.3f} seconds.")


@click.group(
    context_settings=dict(
        show_default=True,
        auto_envvar_prefix=CLI_NAME,
    )
)
@click.option(
    "-m",
    "--manager",
    type=click.Choice(ALL_MANAGER_IDS, case_sensitive=False),
    multiple=True,
    help="Restrict sub-command to a subset of package managers. Repeat to "
    "select multiple managers. The order in which options are provided defines the "
    "order in which sub-commands will process them.",
)
@click.option(
    "-e",
    "--exclude",
    type=click.Choice(ALL_MANAGER_IDS, case_sensitive=False),
    multiple=True,
    help="Exclude a package manager. Repeat to exclude multiple managers.",
)
@click.option(
    "-a",
    "--all-managers",
    is_flag=True,
    default=False,
    help="Force evaluation of all package manager implemented by mpm, even those not"
    "supported by the current platform. Still applies filtering by --manager and "
    "--exclude options before calling the subcommand.",
)
@click.option(
    "-x",
    "--xkcd",
    is_flag=True,
    default=False,
    help=f"Forces the subset of package managers to the order defined in XKCD #1654 "
    "comic, i.e. {XKCD_MANAGER_ORDER}.",
)
@click.option(
    "--ignore-auto-updates/--include-auto-updates",
    default=True,
    help="Report all outdated packages, including those tagged as "
    "auto-updating. Only applies to 'outdated' and 'upgrade' commands.",
)
@click.option(
    "-o",
    "--output-format",
    type=click.Choice(sorted(RENDERING_MODES), case_sensitive=False),
    default="psql_unicode",
    help="Rendering mode of the output.",
)
@click.option(
    "-s",
    "--sort-by",
    type=click.Choice(sorted(SORTABLE_FIELDS), case_sensitive=False),
    default="manager_id",
    help="Sort results.",
)
@click.option(
    "--stats/--no-stats",
    default=True,
    help="Print per-manager package statistics.",
)
@click.option(
    "--time/--no-time",
    default=False,
    help="Measure and print elapsed execution time.",
)
@click.option(
    "--stop-on-error/--continue-on-error",
    default=False,
    help="Stop right away or continue operations on manager CLI error.",
)
@click.option(
    "-d",
    "--dry-run",
    is_flag=True,
    default=False,
    help="Do not actually perform any action, just simulate CLI calls.",
)
@click.option(
    "-C",
    "--config",
    metavar="CONFIG_PATH",
    type=click.Path(path_type=Path, resolve_path=True),
    # default=default_conf_path(),
    help="Location of the configuration file.",
    # Force eagerness so the config option's callback gets the oportunity to set the
    # default_map values before the other options use them.
    is_eager=True,
    callback=load_conf,
    expose_value=False,
)
@click_log.simple_verbosity_option(
    logger,
    default="INFO",
    metavar="LEVEL",
    help="Either CRITICAL, ERROR, WARNING, INFO or DEBUG.",
)
@version_option(
    version=__version__,
    prog_name=CLI_NAME,
    version_color="green",
    prog_name_color="white",
    message=f"%(prog)s %(version)s\n{env_data}",
    message_color="bright_black",
)
@click.help_option("-h", "--help")
@click.pass_context
def cli(
    ctx,
    manager,
    exclude,
    all_managers,
    xkcd,
    ignore_auto_updates,
    output_format,
    sort_by,
    stats,
    time,
    stop_on_error,
    dry_run,
):
    """CLI for multi-package manager upgrades."""
    # Take timestamp snapshot.
    start_time = perf_counter() if time else None

    # Print log level.
    level = logger.level
    level_name = logging._levelToName.get(level, level)
    logger.debug(f"Verbosity set to {level_name}.")

    # Select the subset of manager to target, and apply manager-level options.
    selected_managers = select_managers(
        keep=manager if not xkcd else XKCD_MANAGER_ORDER,
        drop=exclude,
        drop_unsupported=not all_managers,
        # Only keep inactive managers to show them in the "managers" subcommand table.
        # Filters them out in any other subcommand.
        drop_inactive=ctx.invoked_subcommand != "managers",
        # Does the manager should raise on error or not.
        stop_on_error=stop_on_error,
        # Should we include auto-update packages or not?
        ignore_auto_updates=ignore_auto_updates,
        dry_run=dry_run,
    )

    # Silence all log message for JSON rendering unless in debug mode.
    if output_format == "json" and level_name != "DEBUG":
        logger.setLevel(logging.CRITICAL * 2)

    # Setup the table formatter.
    if output_format != "json":
        table_formatter.format_name = output_format

    # Load up global options to the context.
    ctx.obj = {
        "selected_managers": selected_managers,
        "output_format": output_format,
        "sort_by": sort_by,
        "stats": stats,
        "time": time,
        "start_time": start_time,
    }

    ctx.call_on_close(reset_logger)
    ctx.call_on_close(timeit)


@cli.command(short_help="List supported package managers and their location.")
@click.pass_context
def managers(ctx):
    """List all supported package managers and their presence on the system."""
    selected_managers = ctx.obj["selected_managers"]
    output_format = ctx.obj["output_format"]
    sort_by = ctx.obj["sort_by"]

    # Machine-friendly data rendering.
    if output_format == "json":
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
        for manager in selected_managers:
            manager_data[manager.id] = {fid: getattr(manager, fid) for fid in fields}
            # Serialize errors at the last minute to gather all we encountered.
            manager_data[manager.id]["errors"] = list(
                {expt.error for expt in manager.cli_errors}
            )

        click.echo(json(manager_data))
        return

    # Human-friendly content rendering.
    table = []
    for manager in selected_managers:

        # Build up the OS column content.
        os_infos = OK if manager.supported else KO
        if not manager.supported:
            os_infos += "  {} only".format(
                ", ".join(sorted((os_label(os_id) for os_id in manager.platforms)))
            )

        # Build up the CLI path column content.
        cli_infos = "{}  {}".format(
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
                version_infos += f"  {manager.version}"
                if not manager.fresh:
                    version_infos += f" {manager.requirement}"

        table.append(
            (
                manager.name,
                click.style(manager.id, fg="green" if manager.fresh else "red"),
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
        sort_by,
    )


@cli.command(short_help="Sync local package info.")
@click.pass_context
def sync(ctx):
    """Sync local package metadata and info from external sources."""
    selected_managers = ctx.obj["selected_managers"]

    for manager in selected_managers:
        manager.sync()


@cli.command(short_help="Cleanup local data.")
@click.pass_context
def cleanup(ctx):
    """Cleanup local data and temporary artifacts."""
    selected_managers = ctx.obj["selected_managers"]

    for manager in selected_managers:
        manager.cleanup()


@cli.command(short_help="List installed packages.")
@click.pass_context
def installed(ctx):
    """List all packages installed on the system from all managers."""
    selected_managers = ctx.obj["selected_managers"]
    output_format = ctx.obj["output_format"]
    sort_by = ctx.obj["sort_by"]
    stats = ctx.obj["stats"]

    # Build-up a global dict of installed packages per manager.
    installed_data = {}

    for manager in selected_managers:
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
    if output_format == "json":
        click.echo(json(installed_data))
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
        sort_by,
    )

    if stats:
        print_stats(installed_data)


@cli.command(short_help="Search packages.")
@click.option(
    "--extended/--package-name",
    default=False,
    help="Extend search to additional package metadata like description, "
    "instead of restricting it package ID and name.",
)
@click.option(
    "--exact/--fuzzy",
    default=False,
    help="Only returns exact matches, or enable fuzzy search in substrings.",
)
@click.argument("query", type=click.STRING, required=True)
@click.pass_context
def search(ctx, extended, exact, query):
    """Search packages from all managers."""
    selected_managers = ctx.obj["selected_managers"]
    output_format = ctx.obj["output_format"]
    sort_by = ctx.obj["sort_by"]
    stats = ctx.obj["stats"]

    # Build-up a global list of package matches per manager.
    matches = {}

    for manager in selected_managers:

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
    if output_format == "json":
        click.echo(json(matches))
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
                segment = click.style(segment, bold=True, fg="green")
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
        sort_by,
    )

    if stats:
        print_stats(matches)


@cli.command(short_help="Install a package.")
@click.argument("package_id", type=click.STRING, required=True)
@click.pass_context
def install(ctx, package_id):
    """Install the provided package using one of the provided package manager."""
    selected_managers = list(ctx.obj["selected_managers"])

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

        click.echo(output)
        return


@cli.command(short_help="List outdated packages.")
@click.option(
    "-c",
    "--cli-format",
    type=click.Choice(sorted(CLI_FORMATS), case_sensitive=False),
    default="plain",
    help="Format of CLI fields in JSON output.",
)
@click.pass_context
def outdated(ctx, cli_format):
    """List available package upgrades and their versions for each manager."""
    selected_managers = ctx.obj["selected_managers"]
    output_format = ctx.obj["output_format"]
    sort_by = ctx.obj["sort_by"]
    stats = ctx.obj["stats"]

    render_cli = partial(PackageManager.render_cli, cli_format=cli_format)

    # Build-up a global list of outdated packages per manager.
    outdated_data = {}

    for manager in selected_managers:

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
                upgrade_all_cli = [CLI_NAME, "--manager", manager.id, "upgrade"]
            outdated_data[manager.id]["upgrade_all_cli"] = render_cli(upgrade_all_cli)

        # Serialize errors at the last minute to gather all we encountered.
        outdated_data[manager.id]["errors"] = list(
            {expt.error for expt in manager.cli_errors}
        )

    # Machine-friendly data rendering.
    if output_format == "json":
        click.echo(json(outdated_data))
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
        sort_by,
    )

    if stats:
        print_stats(outdated_data)


@cli.command(short_help="Upgrade all packages.")
@click.pass_context
def upgrade(ctx):
    """Perform a full package upgrade on all available managers."""
    selected_managers = ctx.obj["selected_managers"]

    for manager in selected_managers:
        logger.info(f"Updating all outdated packages from {manager.id}...")
        try:
            output = manager.upgrade_all()
        except NotImplementedError:
            logger.warning(f"{manager.id} does not implement upgrade command.")
            continue

        if output:
            logger.info(output)


@cli.command(short_help="Save installed packages to a TOML file.")
@click.argument("toml_output", type=click.File("w"), default="-")
@click.pass_context
def backup(ctx, toml_output):
    """Dump the list of installed packages to a TOML file.

    By default the generated TOML content is displayed directly in the console
    output. So `mpm backup` is the same as a call to `mpm backup -`. To have
    the result written in a file on disk, specify the output file like so:
    `mpm backup ./mpm-packages.toml`.

    The TOML file can then be safely consumed by the `mpm restore` command.
    """
    selected_managers = ctx.obj["selected_managers"]
    stats = ctx.obj["stats"]

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
    doc = f"# Generated by {CLI_NAME} {__version__}.\n"
    doc += "# Timestamp: {}.\n".format(datetime.now().isoformat())

    installed_data = {}

    # Create one section for each package manager.
    for manager in selected_managers:
        logger.info(f"Dumping packages from {manager.id}...")
        installed_packages = manager.installed.values()

        # Prepare data for stats.
        installed_data[manager.id] = {
            "id": manager.id,
            "packages": installed_packages,
        }

        pkg_data = dict(
            sorted(((p["id"], str(p["installed_version"])) for p in installed_packages))
        )

        if pkg_data:
            doc += "\n" + tomli_w.dumps({manager.id: pkg_data})

    toml_output.write(doc)

    if stats:
        print_stats(installed_data)


@cli.command(short_help="Install packages in batch as specified by TOML files.")
@click.argument("toml_files", type=click.File("r"), required=True, nargs=-1)
@click.pass_context
def restore(ctx, toml_files):
    """Read TOML files then install or upgrade each package referenced in
    them.

    Version specified in the TOML file is ignored in the current implementation.
    """
    selected_managers = ctx.obj["selected_managers"]

    for toml_input in toml_files:

        is_stdin = isinstance(toml_input, TextIOWrapper)
        toml_filepath = toml_input.name if is_stdin else Path(toml_input.name).resolve()
        logger.info(f"Load package list from {toml_filepath}")

        doc = tomli.loads(toml_input.read())

        # List unrecognized sections.
        ignored_sections = [
            f"[{section}]" for section in doc if section not in ALL_MANAGER_IDS
        ]
        if ignored_sections:
            plural = "s" if len(ignored_sections) > 1 else ""
            sections = ", ".join(ignored_sections)
            logger.info(f"Ignore {sections} section{plural}.")

        for manager in selected_managers:
            if manager.id not in doc:
                logger.warning(f"No [{manager.id}] section found.")
                continue
            logger.info(f"Restore {manager.id} packages...")
            for package_id, version in doc[manager.id].items():
                output = manager.install(package_id)
                click.echo(output)
