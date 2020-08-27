# -*- coding: utf-8 -*-
#
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

import functools
import logging
import re
from datetime import datetime
from functools import partial
from io import TextIOWrapper
from operator import getitem, itemgetter
from pathlib import Path
from sys import __stdin__, __stdout__
from time import time as time_now

import click
import click_log
import tomlkit
from boltons.cacheutils import LRI, cached
from boltons.strutils import complement_int_list, int_ranges_from_int_list, strip_ansi
from cli_helpers.tabular_output import TabularOutputFormatter
from simplejson import dumps as json_dumps

from . import __version__, logger, CLI_NAME
from .base import CLI_FORMATS, CLIError, PackageManager
from .managers import pool
from .platform import CURRENT_OS_ID, WINDOWS, os_label
from .version import TokenizedString

# Initialize the table formatter.
table_formatter = TabularOutputFormatter()


# Register all rendering modes for table data.
RENDERING_MODES = {"json"}
RENDERING_MODES.update(table_formatter.supported_formats)
RENDERING_MODES = frozenset(RENDERING_MODES)

# List of unicode rendering modes that will fall back to ascii on windows.
# Windows has some hard time printing unicode characters to console output. It
# seems to be an effect of cp1252 encoding and/or click not able to transcode
# chars. Here is the traceback:
#
# File "(...)\meta_package_manager\cli.py", line 133, in print_table
#   click.echo(line)
# File "(...)\site-packages\click\utils.py", line 272, in echo
#   file.write(message)
# File "(...)\lib\encodings\cp1252.py", line 19, in encode
#   return codecs.charmap_encode(input,self.errors,encoding_table)[0]
# UnicodeEncodeError: 'charmap' codec can't encode characters in position
#   0-140: character maps to <undefined>
#
# Fortunately, I found the fundamental issue and I no longer need to blacklist
# some rendering modes. See: a3008f8c3a42efedd88378f087202b73d907bbb7 . I'll
# still keep the construct around just in case I need to quickly blacklist
# some.
WINDOWS_MODE_BLACKLIST = frozenset([])

# List of fields IDs allowed to be sorted.
SORTABLE_FIELDS = {
    "manager_id",
    "manager_name",
    "package_id",
    "package_name",
    "version",
}

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
    """ Utility to print a table and sort its content. """
    # Do not print anything, not even table headers if no rows.
    if not rows:
        return

    header_labels = [label for label, _ in header_defs]

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
    """ Print statistics. """
    manager_stats = {infos["id"]: len(infos["packages"]) for infos in data.values()}
    total_installed = sum(manager_stats.values())
    per_manager_totals = ", ".join(
        [
            "{}: {}".format(k, v)
            for k, v in sorted(manager_stats.items(), key=itemgetter(1), reverse=True)
        ]
    )
    if per_manager_totals:
        per_manager_totals = " ({})".format(per_manager_totals)
    plural = "s" if total_installed > 1 else ""
    click.echo(f"{total_installed} package{plural} total{per_manager_totals}.")


class timeit:
    """Decorator to measure and print elapsed execution time of a function."""

    def __call__(self, func):
        @functools.wraps(func)
        def decorated(*args, **kwargs):
            with self:
                return func(*args, **kwargs)

        return decorated

    def __enter__(self):
        self.measure_time = click.get_current_context().obj["time"]
        if self.measure_time:
            self.start_time = time_now()

    def __exit__(self, *args, **kwargs):
        if self.measure_time:
            elapsed = time_now() - self.start_time
            click.echo(f"Execution time: {elapsed:.3} seconds.")


@click.group()
@click_log.simple_verbosity_option(
    logger,
    default="INFO",
    metavar="LEVEL",
    help="Either CRITICAL, ERROR, WARNING, INFO or DEBUG. Defaults to INFO.",
)
@click.option(
    "-m",
    "--manager",
    type=click.Choice(pool()),
    multiple=True,
    help="Restrict sub-command to a subset of package managers. Repeat to "
    "select multiple managers. Defaults to all.",
)
@click.option(
    "-e",
    "--exclude",
    type=click.Choice(pool()),
    multiple=True,
    help="Exclude a package manager. Repeat to exclude multiple managers. "
    "Defaults to none.",
)
@click.option(
    "--ignore-auto-updates/--include-auto-updates",
    default=True,
    help="Report all outdated packages, including those tagged as "
    "auto-updating. Defaults to include all packages. Only applies to "
    "'outdated' and 'upgrade' commands.",
)
@click.option(
    "-o",
    "--output-format",
    type=click.Choice(sorted(RENDERING_MODES)),
    default="fancy_grid",
    help="Rendering mode of the output. Defaults to fancy-grid.",
)
@click.option(
    "-s",
    "--sort-by",
    type=click.Choice(SORTABLE_FIELDS),
    default="manager_id",
    help="Sort results. Defaults to manager_id.",
)
@click.option(
    "--stats/--no-stats",
    default=True,
    help="Print per-manager package statistics. Active by default.",
)
@click.option(
    "--time/--no-time",
    default=False,
    help="Measure and print elapsed execution time. Inactive by default.",
)
@click.option(
    "--stop-on-error/--continue-on-error",
    default=True,
    help="Stop right "
    "away or continue operations on manager CLI error. Defaults to stop.",
)
@click.version_option(__version__)
@click.pass_context
def cli(
    ctx,
    manager,
    exclude,
    ignore_auto_updates,
    output_format,
    sort_by,
    stats,
    time,
    stop_on_error,
):
    """ CLI for multi-package manager upgrades. """
    # TODO: merge CLI parameters and config file here.
    # See: https://github.com/kdeldycke/meta-package-manager/issues/66

    level = logger.level
    level_name = logging._levelToName.get(level, level)
    logger.debug(f"Verbosity set to {level_name}.")

    # Target all available managers by default.
    target_ids = set(pool())
    # Only keeps the subset of selected by the user.
    if manager:
        target_ids = target_ids.intersection(manager)
    # Remove managers excluded by the user.
    target_ids = target_ids.difference(exclude)
    target_managers = [pool()[mid] for mid in sorted(target_ids)]

    # Apply manager-level options.
    for m_obj in target_managers:
        # Does the manager should raise on error or not.
        m_obj.raise_on_error = stop_on_error
        # Should we include auto-update packages or not?
        m_obj.ignore_auto_updates = ignore_auto_updates

    # Pre-filters inactive managers.
    def keep_available(manager):
        if manager.available:
            return True
        logger.warning(f"Skip unavailable {manager.id} manager.")

    # Use an iterator to not trigger log messages for the 'managers' subcommand
    # which is not using this variable.
    active_managers = filter(keep_available, target_managers)

    # Silence all log message for JSON rendering unless in debug mode.
    if output_format == "json" and level_name != "DEBUG":
        logger.setLevel(logging.CRITICAL * 2)

    # Setup the table formatter.
    if output_format != "json":

        # Fallback unicode-rendering to safe ascii on Windows.
        if CURRENT_OS_ID == WINDOWS and output_format in WINDOWS_MODE_BLACKLIST:
            output_format = "ascii"

        table_formatter.format_name = output_format

    # Load up global options to the context.
    ctx.obj = {
        "target_managers": target_managers,
        "active_managers": active_managers,
        "output_format": output_format,
        "sort_by": sort_by,
        "stats": stats,
        "time": time,
    }


@cli.command(short_help="List supported package managers and their location.")
@click.pass_context
@timeit()
def managers(ctx):
    """List all supported package managers and their presence on the system."""
    target_managers = ctx.obj["target_managers"]
    output_format = ctx.obj["output_format"]
    sort_by = ctx.obj["sort_by"]

    # Machine-friendly data rendering.
    if output_format == "json":
        manager_data = {}
        # Build up the data structure of manager metadata.
        fields = [
            "name",
            "id",
            "supported",
            "cli_path",
            "executable",
            "version",
            "fresh",
            "available",
        ]
        for manager in target_managers:
            manager_data[manager.id] = {fid: getattr(manager, fid) for fid in fields}
            # Serialize errors at the last minute to gather all we encountered.
            manager_data[manager.id]["errors"] = list(
                {expt.error for expt in manager.cli_errors}
            )

        click.echo(json(manager_data))
        return

    # Human-friendly content rendering.
    table = []
    for manager in target_managers:

        # Build up the OS column content.
        os_infos = OK if manager.supported else KO
        if not manager.supported:
            os_infos += "  {} only".format(
                ", ".join(sorted([os_label(os_id) for os_id in manager.platforms]))
            )

        # Build up the CLI path column content.
        cli_infos = "{}  {}".format(
            OK if manager.cli_path else KO,
            manager.cli_path
            if manager.cli_path
            else "{!r} not found".format(manager.cli_name),
        )

        # Build up the version column content.
        version_infos = ""
        if manager.executable:
            version_infos = OK if manager.fresh else KO
            if manager.version:
                version_infos += "  {}".format(manager.version)
                if not manager.fresh:
                    version_infos += " {}".format(manager.requirement)

        table.append(
            [
                manager.name,
                click.style(manager.id, fg="green" if manager.fresh else "red"),
                os_infos,
                cli_infos,
                OK if manager.executable else "",
                version_infos,
            ]
        )

    print_table(
        [
            ("Package manager", "manager_name"),
            ("ID", "manager_id"),
            ("Supported", None),
            ("CLI", None),
            ("Executable", None),
            ("Version", "version"),
        ],
        table,
        sort_by,
    )


@cli.command(short_help="Sync local package info.")
@click.pass_context
@timeit()
def sync(ctx):
    """ Sync local package metadata and info from external sources. """
    active_managers = ctx.obj["active_managers"]

    for manager in active_managers:
        manager.sync()


@cli.command(short_help="Cleanup local data.")
@click.pass_context
@timeit()
def cleanup(ctx):
    """ Cleanup local data and temporary artifacts. """
    active_managers = ctx.obj["active_managers"]

    for manager in active_managers:
        manager.cleanup()


@cli.command(short_help="List installed packages.")
@click.pass_context
@timeit()
def installed(ctx):
    """ List all packages installed on the system from all managers. """
    active_managers = ctx.obj["active_managers"]
    output_format = ctx.obj["output_format"]
    sort_by = ctx.obj["sort_by"]
    stats = ctx.obj["stats"]

    # Build-up a global dict of installed packages per manager.
    installed_data = {}

    for manager in active_managers:
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
            [
                info["name"],
                info["id"],
                manager_id,
                info["installed_version"] if info["installed_version"] else "?",
            ]
            for info in installed_pkg["packages"]
        ]

    # Sort and print table.
    print_table(
        [
            ("Package name", "package_name"),
            ("ID", "package_id"),
            ("Manager", "manager_id"),
            ("Installed version", "version"),
        ],
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
    "instead of restricting it package ID and name. Defaults to package ID "
    "search.",
)
@click.option(
    "--exact/--fuzzy",
    default=False,
    help="Only returns exact matches, or enable fuzzy search in substrings. "
    "Fuzzy by default.",
)
@click.argument("query", type=click.STRING, required=True)
@click.pass_context
@timeit()
def search(ctx, extended, exact, query):
    """ Search packages from all managers. """
    active_managers = ctx.obj["active_managers"]
    output_format = ctx.obj["output_format"]
    sort_by = ctx.obj["sort_by"]
    stats = ctx.obj["stats"]

    # Build-up a global list of package matches per manager.
    matches = {}

    for manager in active_managers:
        matches[manager.id] = {
            "id": manager.id,
            "name": manager.name,
            "packages": list(manager.search(query, extended, exact).values()),
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

        # TODO: Fix upper-case matching, as tokenizer lower them down.

        for part in query_parts:
            # Search for occurrences of query parts in original string.
            if part in string:
                # Flag matching substrings for highlighting.
                occurrences = [match.start() for match in re.finditer(part, string)]

                for match_start in occurrences:
                    match_end = match_start + len(part) - 1
                    ranges.add("{}-{}".format(match_start, match_end))

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
                segment = click.style(segment, bold=True)
            styled_str += segment

        return styled_str

    # Human-friendly content rendering.
    table = []
    for manager_id, matching_pkg in matches.items():
        table += [
            [
                highlight(info["name"]),
                highlight(info["id"]),
                manager_id,
                info["latest_version"] if info["latest_version"] else "?",
            ]
            for info in matching_pkg["packages"]
        ]

    # Sort and print table.
    print_table(
        [
            ("Package name", "package_name"),
            ("ID", "package_id"),
            ("Manager", "manager_id"),
            ("Latest version", "version"),
        ],
        table,
        sort_by,
    )

    if stats:
        print_stats(matches)


@cli.command(short_help="List outdated packages.")
@click.option(
    "-c",
    "--cli-format",
    type=click.Choice(CLI_FORMATS),
    default="plain",
    help="Format of CLI fields in JSON output. Defaults to plain.",
)
@click.pass_context
@timeit()
def outdated(ctx, cli_format):
    """List available package upgrades and their versions for each manager."""
    active_managers = ctx.obj["active_managers"]
    output_format = ctx.obj["output_format"]
    sort_by = ctx.obj["sort_by"]
    stats = ctx.obj["stats"]

    render_cli = partial(PackageManager.render_cli, cli_format=cli_format)

    # Build-up a global list of outdated packages per manager.
    outdated_data = {}

    for manager in active_managers:

        packages = list(map(dict, manager.outdated.values()))
        for info in packages:
            info.update({"upgrade_cli": render_cli(manager.upgrade_cli(info["id"]))})

        outdated_data[manager.id] = {
            "id": manager.id,
            "name": manager.name,
            "packages": packages,
        }

        # Do not include the full-upgrade CLI if we did not detect any outdated
        # package.
        if manager.outdated:
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
            [
                info["name"],
                info["id"],
                manager_id,
                info["installed_version"] if info["installed_version"] else "?",
                info["latest_version"],
            ]
            for info in outdated_pkg["packages"]
        ]

    # Sort and print table.
    print_table(
        [
            ("Package name", "package_name"),
            ("ID", "package_id"),
            ("Manager", "manager_id"),
            ("Installed version", "version"),
            ("Latest version", None),
        ],
        table,
        sort_by,
    )

    if stats:
        print_stats(outdated_data)


@cli.command(short_help="Upgrade all packages.")
@click.option(
    "-d",
    "--dry-run",
    is_flag=True,
    default=False,
    help="Do not actually perform any upgrade, just simulate CLI calls.",
)
@click.pass_context
@timeit()
def upgrade(ctx, dry_run):
    """ Perform a full package upgrade on all available managers. """
    active_managers = ctx.obj["active_managers"]

    for manager in active_managers:

        logger.info(f"Updating all outdated packages from {manager.id}...")

        try:
            output = manager.upgrade_all(dry_run=dry_run)
        except CLIError as expt:
            logger.error(expt.error)

        if output:
            logger.info(output)


@cli.command(short_help="Save installed packages to a TOML file.")
@click.argument("toml_output", type=click.File("w"), default="-")
@click.pass_context
@timeit()
def backup(ctx, toml_output):
    """Dump the list of installed packages to a TOML file.

    By default the generated TOML content is displayed directly in the console
    output. So `mpm backup` is the same as a call to `mpm backup -`. To have
    the result written in a file on disk, specify the output file like so:
    `mpm backup ./mpm-packages.toml`.

    The TOML file can then be safely consumed by the `mpm restore` command.
    """
    active_managers = ctx.obj["active_managers"]
    stats = ctx.obj["stats"]

    # XXX Hack for unittests to pass, while we wait for
    # https://github.com/pallets/click/pull/1497
    if isinstance(toml_output, TextIOWrapper):
        toml_output = __stdout__

    is_stdout = toml_output is __stdout__
    toml_filepath = toml_output.name if is_stdout else Path(toml_output.name).resolve()
    logger.info(f"Backup package list to {toml_filepath}")

    if not is_stdout:
        if toml_filepath.exists() and not toml_filepath.is_file():
            logger.error("Target file exist and is not a file.")
            return
        if toml_filepath.suffix.lower() != ".toml":
            logger.error("Target file is not a TOML file.")
            return

    # Initialize the TOML structure.
    doc = tomlkit.document()
    # Leave some metadata as comment.
    doc.add(tomlkit.comment("Generated by {} {}.".format(CLI_NAME, __version__)))
    doc.add(tomlkit.comment("Timestamp: {}.".format(datetime.now().isoformat())))

    installed_data = {}

    # Create one section for each package manager.
    for manager in active_managers:
        logger.info(f"Dumping packages from {manager.id}...")

        # Prepare data for stats.
        installed_data[manager.id] = {
            "id": manager.id,
            "packages": manager.installed.values(),
        }

        manager_section = tomlkit.table()
        pkg_data = sorted(
            [(p["id"], p["installed_version"]) for p in manager.installed.values()]
        )
        for package_id, package_version in pkg_data:
            # Version specifier is inspired by Poetry.
            manager_section.add(package_id, "^{}".format(package_version))
        if pkg_data:
            doc.add(manager.id, manager_section)

    toml_output.write(tomlkit.dumps(doc, sort_keys=True))

    if stats:
        print_stats(installed_data)


@cli.command(short_help="Install packages in batch as specified by TOML files.")
@click.argument("toml_files", type=click.File("r"), required=True, nargs=-1)
@click.pass_context
@timeit()
def restore(ctx, toml_files):
    """Read TOML files then install or upgrade each package referenced in
    them.
    """
    active_managers = ctx.obj["active_managers"]

    for toml_input in toml_files:

        toml_filepath = (
            toml_input.name
            if toml_input is __stdin__
            else Path(toml_input.name).resolve()
        )
        logger.info(f"Load package list from {toml_filepath}")

        doc = tomlkit.parse(toml_input.read())

        # List unrecognized sections.
        ignored_sections = [
            "[{}]".format(section) for section in doc if section not in pool()
        ]
        if ignored_sections:
            plural = "s" if len(ignored_sections) > 1 else ""
            sections = ", ".join(ignored_sections)
            logger.warning(f"Ignore {sections} section{plural}.")

        for manager in active_managers:
            if manager.id not in doc:
                logger.warning(f"No [{manager.id}] section found.")
                continue
            logger.info(f"Restore {manager.id} packages...")
            logger.warning("Installation of packages not implemented yet.")
            # for package_id, version in doc[manager.id].items():
            #    raise NotImplemented
