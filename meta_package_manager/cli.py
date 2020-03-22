# -*- coding: utf-8 -*-
#
# Copyright (c) 2016-2018 Kevin Deldycke <kevin@deldycke.com>
#                         and contributors.
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
from datetime import datetime
from functools import partial
from operator import itemgetter
from os import path
from sys import __stdin__, __stdout__

import click
import click_log
import tomlkit
from cli_helpers.tabular_output import TabularOutputFormatter
from simplejson import dumps as json_dumps

from . import __version__, logger
from .base import CLI_FORMATS, CLIError, PackageManager
from .managers import pool
from .platform import os_label

# Initialize the table formatter.
table_formatter = TabularOutputFormatter()


# Register all rendering modes for table data.
RENDERING_MODES = set(['json'])
RENDERING_MODES.update(table_formatter.supported_formats)


# Pre-rendered UI-elements.
OK = click.style(u'✓', fg='green')
KO = click.style(u'✘', fg='red')


click_log.basic_config(logger)


def json(data):
    """ Utility function to render data structure into pretty printed JSON. """
    return json_dumps(data, sort_keys=True, indent=4, separators=(',', ': '))


def print_table(headers, rows):
    """ Utility to handle printing of a table. """
    for line in table_formatter.format_output(rows, headers):
        logger.info(line)


def print_stats(data):
    """ Print statistics. """
    manager_stats = {
        infos['id']: len(infos['packages']) for infos in data.values()}
    total_installed = sum(manager_stats.values())
    per_manager_totals = ', '.join([
        '{} from {}'.format(v, k)
        for k, v in sorted(manager_stats.items())])
    if per_manager_totals:
        per_manager_totals = ' ({})'.format(per_manager_totals)
    logger.info('{} package{} found{}.'.format(
        total_installed,
        's' if total_installed > 1 else '',
        per_manager_totals))


@click.group()
@click_log.simple_verbosity_option(
    logger, default='INFO', metavar='LEVEL',
    help='Either CRITICAL, ERROR, WARNING, INFO or DEBUG. Defaults to INFO.')
@click.option(
    '-m', '--manager', type=click.Choice(sorted(pool())), multiple=True,
    help="Restrict sub-command to a subset of package managers. Repeat to "
    "select multiple managers. Defaults to all.")
@click.option(
    '-e', '--exclude', type=click.Choice(sorted(pool())), multiple=True,
    help="Exclude a package manager. Repeat to exclude multiple managers. "
    "Defaults to none.")
@click.option(
    '--ignore-auto-updates/--include-auto-updates', default=True,
    help="Report all outdated packages, including those tagged as "
    "auto-updating. Defaults to include all packages. Only applies for "
    "'outdated' and 'upgrade' commands.")
@click.option(
    '-o', '--output-format', type=click.Choice(sorted(RENDERING_MODES)),
    default='fancy_grid',
    help="Rendering mode of the output. Defaults to fancy-grid.")
@click.option(
    '--stats/--no-stats', default=True,
    help="Print statistics or not at the end of output. Active by default.")
@click.option(
    '--stop-on-error/--continue-on-error', default=True, help="Stop right "
    "away or continue operations on manager CLI error. Defaults to stop.")
@click.version_option(__version__)
@click.pass_context
def cli(ctx, manager, exclude, ignore_auto_updates, output_format, stats,
        stop_on_error):
    """ CLI for multi-package manager upgrades. """
    level = logger.level
    level_name = logging._levelToName.get(level, level)
    logger.debug('Verbosity set to {}.'.format(level_name))

    # Target all available managers by default.
    target_ids = set(pool())
    # Only keeps the subset of selected by the user.
    if manager:
        target_ids = target_ids.intersection(manager)
    # Remove managers excluded by the user.
    target_ids = target_ids.difference(exclude)
    target_managers = [m for mid, m in pool().items() if mid in target_ids]

    # Apply manager-level options.
    for m in target_managers:
        # Does the manager should raise on error or not.
        m.raise_on_error = stop_on_error
        # Should we include auto-update packages or not?
        m.ignore_auto_updates = ignore_auto_updates

    # Pre-filters inactive managers.
    def keep_available(manager):
        if manager.available:
            return True
        logger.warning('Skip unavailable {} manager.'.format(manager.id))
    # Use an iterator to not trigger log messages for subcommands not using
    # this variable.
    active_managers = filter(keep_available, target_managers)

    # Silence all log message for JSON rendering unless in debug mode.
    if output_format == 'json' and level_name != 'DEBUG':
        logger.setLevel(logging.CRITICAL * 2)

    # Setup the table formatter.
    if output_format != 'json':
        table_formatter.format_name = output_format

    # Load up global options to the context.
    ctx.obj = {
        'target_managers': target_managers,
        'active_managers': active_managers,
        'output_format': output_format,
        'stats': stats}


@cli.command(short_help='List supported package managers and their location.')
@click.pass_context
def managers(ctx):
    """ List all supported package managers and their presence on the system.
    """
    target_managers = ctx.obj['target_managers']
    output_format = ctx.obj['output_format']

    # Machine-friendly data rendering.
    if output_format == 'json':
        manager_data = {}
        # Build up the data structure of manager metadata.
        fields = [
            'name', 'id', 'supported', 'cli_path', 'executable',
            'version_string', 'fresh', 'available']
        for manager in target_managers:
            manager_data[manager.id] = {
                fid: getattr(manager, fid) for fid in fields}
            # Serialize errors at the last minute to gather all we encountered.
            manager_data[manager.id]['errors'] = list({
                expt.error for expt in manager.cli_errors})

        # JSON mode use echo to output data because the logger is disabled.
        click.echo(json(manager_data))
        return

    # Human-friendly content rendering.
    table = []
    for manager in target_managers:

        # Build up the OS column content.
        os_infos = OK if manager.supported else KO
        if not manager.supported:
            os_infos += "  {} only".format(', '.join(sorted([
                os_label(os_id) for os_id in manager.platforms])))

        # Build up the CLI path column content.
        cli_infos = u"{}  {}".format(
            OK if manager.cli_path else KO,
            manager.cli_path if manager.cli_path
            else "{} CLI not found.".format(manager.cli_name))

        # Build up the version column content.
        version_infos = ''
        if manager.executable:
            version_infos = OK if manager.fresh else KO
            if manager.version:
                version_infos += "  {}".format(manager.version_string)
                if not manager.fresh:
                    version_infos += " {}".format(manager.requirement)

        table.append([
            manager.name,
            manager.id,
            os_infos,
            cli_infos,
            OK if manager.executable else '',
            version_infos])

    print_table(
        ['Package manager', 'ID', 'Supported', 'CLI', 'Executable', 'Version'],
        sorted(table, key=itemgetter(1)))


@cli.command(short_help='Sync local package info.')
@click.pass_context
def sync(ctx):
    """ Sync local package metadata and info from external sources. """
    active_managers = ctx.obj['active_managers']

    for manager in active_managers:
        manager.sync()


@cli.command(short_help='List installed packages.')
@click.pass_context
def installed(ctx):
    """ List all packages installed on the system from all managers. """
    active_managers = ctx.obj['active_managers']
    output_format = ctx.obj['output_format']
    stats = ctx.obj['stats']

    # Build-up a global list of installed packages per manager.
    installed = {}

    for manager in active_managers:
        installed[manager.id] = {
            'id': manager.id,
            'name': manager.name,
            'packages': list(manager.installed.values())}

        # Serialize errors at the last minute to gather all we encountered.
        installed[manager.id]['errors'] = list({
            expt.error for expt in manager.cli_errors})

    # Machine-friendly data rendering.
    if output_format == 'json':
        # JSON mode use echo to output data because the logger is disabled.
        click.echo(json(installed))
        return

    # Human-friendly content rendering.
    table = []
    for manager_id, installed_pkg in installed.items():
        table += [[
            info['name'],
            info['id'],
            manager_id,
            info['installed_version'] if info['installed_version'] else '?']
            for info in installed_pkg['packages']]

    def sort_method(line):
        """ Force sorting of table.

        By lower-cased package name and ID first, then manager ID.
        """
        return line[0].lower(), line[1].lower(), line[2]

    # Sort and print table.
    print_table(
        ['Package name', 'ID', 'Manager', 'Installed version'],
        sorted(table, key=sort_method))

    if stats:
        print_stats(installed)


@cli.command(short_help='Search packages.')
@click.argument('query', type=click.STRING, required=True)
@click.pass_context
def search(ctx, query):
    """ Search packages from all managers. """
    active_managers = ctx.obj['active_managers']
    output_format = ctx.obj['output_format']
    stats = ctx.obj['stats']

    # Build-up a global list of package matches per manager.
    matches = {}

    for manager in active_managers:
        matches[manager.id] = {
            'id': manager.id,
            'name': manager.name,
            'packages': list(manager.search(query).values())}

        # Serialize errors at the last minute to gather all we encountered.
        matches[manager.id]['errors'] = list({
            expt.error for expt in manager.cli_errors})

    # Machine-friendly data rendering.
    if output_format == 'json':
        # JSON mode use echo to output data because the logger is disabled.
        click.echo(json(matches))
        return

    # Human-friendly content rendering.
    table = []
    for manager_id, matching_pkg in matches.items():
        table += [[
            info['name'],
            info['id'],
            manager_id,
            info['latest_version'] if info['latest_version'] else '?']
            for info in matching_pkg['packages']]

    def sort_method(line):
        """ Force sorting of table.

        By lower-cased package name and ID first, then manager ID.
        """
        return line[0].lower(), line[1].lower(), line[2]

    # Sort and print table.
    # TODO: highlight exact matches.
    print_table(
        ['Package name', 'ID', 'Manager', 'Latest version'],
        sorted(table, key=sort_method))

    if stats:
        print_stats(matches)


@cli.command(short_help='List outdated packages.')
@click.option(
    '-c', '--cli-format', type=click.Choice(CLI_FORMATS), default='plain',
    help="Format of CLI fields in JSON output. Defaults to plain.")
@click.pass_context
def outdated(ctx, cli_format):
    """ List available package upgrades and their versions for each manager.
    """
    active_managers = ctx.obj['active_managers']
    output_format = ctx.obj['output_format']
    stats = ctx.obj['stats']

    render_cli = partial(PackageManager.render_cli, cli_format=cli_format)

    # Build-up a global list of outdated packages per manager.
    outdated = {}

    for manager in active_managers:

        packages = list(map(dict, manager.outdated.values()))
        for info in packages:
            info.update({
                'upgrade_cli': render_cli(manager.upgrade_cli(info['id']))})

        outdated[manager.id] = {
            'id': manager.id,
            'name': manager.name,
            'packages': packages}

        # Do not include the full-upgrade CLI if we did not detect any outdated
        # package.
        if manager.outdated:
            try:
                upgrade_all_cli = manager.upgrade_all_cli()
            except NotImplementedError:
                # Fallback on mpm itself which is capable of simulating a full
                # upgrade.
                upgrade_all_cli = ['mpm', '--manager', manager.id, 'upgrade']
            outdated[manager.id]['upgrade_all_cli'] = render_cli(
                upgrade_all_cli)

        # Serialize errors at the last minute to gather all we encountered.
        outdated[manager.id]['errors'] = list({
            expt.error for expt in manager.cli_errors})

    # Machine-friendly data rendering.
    if output_format == 'json':
        # JSON mode use echo to output data because the logger is disabled.
        click.echo(json(outdated))
        return

    # Human-friendly content rendering.
    table = []
    for manager_id, outdated_pkg in outdated.items():
        table += [[
            info['name'],
            info['id'],
            manager_id,
            info['installed_version'] if info['installed_version'] else '?',
            info['latest_version']]
            for info in outdated_pkg['packages']]

    def sort_method(line):
        """ Force sorting of table.

        By lower-cased package name and ID first, then manager ID.
        """
        return line[0].lower(), line[1].lower(), line[2]

    # Sort and print table.
    print_table(
        ['Package name', 'ID', 'Manager', 'Installed version',
         'Latest version'],
        sorted(table, key=sort_method))

    if stats:
        print_stats(outdated)


@cli.command(short_help='Upgrade all packages.')
@click.option(
    '-d', '--dry-run', is_flag=True, default=False,
    help='Do not actually perform any upgrade, just simulate CLI calls.')
@click.pass_context
def upgrade(ctx, dry_run):
    """ Perform a full package upgrade on all available managers. """
    active_managers = ctx.obj['active_managers']

    for manager in active_managers:

        logger.info(
            'Updating all outdated packages from {}...'.format(manager.id))

        try:
            output = manager.upgrade_all(dry_run=dry_run)
        except CLIError as expt:
            logger.error(expt.error)

        if output:
            logger.info(output)


@cli.command(short_help='Save installed packages to a TOML file.')
@click.argument('toml_output', type=click.File('w'), default='-')
@click.pass_context
def backup(ctx, toml_output):
    """ Dump the list of installed packages to a TOML file.

    By default the generated TOML content is displayed directly in the console
    output. So `mpm backup` is the same as a call to `mpm backup -`. To have
    the result written in a file on disk, specify the output file like so:
    `mpm backup ./mpm-packages.toml`.

    The TOML file can then be safely consumed by the `mpm restore` command.
    """
    active_managers = ctx.obj['active_managers']

    is_stdout = toml_output is __stdout__
    toml_filepath = toml_output.name if is_stdout else path.abspath(
        toml_output.name)
    logger.info(
        'Backup list of installed packages to: {}'.format(toml_filepath))

    if not is_stdout:
        if path.exists(toml_filepath) and not path.isfile(toml_filepath):
            logger.error('Target file exist and is not a file.')
            return
        if path.splitext(toml_filepath)[1].lower() != '.toml':
            logger.error('Target file is not a TOML file.')
            return

    # Initialize the TOML structure.
    doc = tomlkit.document()
    # Leave some metadata as comment.
    doc.add(tomlkit.comment(
        "Generated by mpm {}.".format(__version__)))
    doc.add(tomlkit.comment(
        "Timestamp: {}.".format(datetime.now().isoformat())))

    # Create one section for each package manager.
    for manager in active_managers:
        logger.info('Dumping packages from {}...'.format(manager.id))

        manager_section = tomlkit.table()
        for package_id, package_version in sorted([
                (p['id'], p['installed_version'])
                for p in manager.installed.values()]):
            # Version specifier is inspired by Poetry.
            manager_section.add(package_id, "^{}".format(package_version))
        doc.add(manager.id, manager_section)

    toml_output.write(tomlkit.dumps(doc))


@cli.command(
    short_help='Install packages in batch as specified by TOML files.')
@click.argument('toml_files', type=click.File('r'), required=True, nargs=-1)
@click.pass_context
def restore(ctx, toml_files):
    """ Read TOML files then install or upgrade each package referenced in
    them.
    """
    active_managers = ctx.obj['active_managers']
    active_manager_ids = [m.id for m in active_managers]

    for toml_input in toml_files:

        toml_filepath = (
            toml_input.name if toml_input is __stdin__
            else path.abspath(toml_input.name))
        logger.info(
            'Load list of packages to install from: {}'.format(toml_filepath))

        doc = tomlkit.parse(toml_input.read())

        for manager_id, packages in doc.items():
            if manager_id not in active_manager_ids:
                continue
            logger.info('Restore {} packages...'.format(manager_id))
            logger.warning("Installation of packages not supported yet.")
            # for package_id, version in packages.items():
            #    raise NotImplemented
