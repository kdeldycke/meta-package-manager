# -*- coding: utf-8 -*-
#
# Copyright (c) 2016 Kevin Deldycke <kevin@deldycke.com>
#                    and contributors.
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

from __future__ import absolute_import, division, print_function

import logging
from functools import partial
from json import dumps as json_dumps
from operator import itemgetter

import click
import click_log
from tabulate import tabulate

from . import __version__, logger
from .base import CLI_FORMATS, CLIError, PackageManager
from .managers import pool
from .platform import os_label

# Output rendering modes. Sorted from most machine-readable to fanciest
# human-readable.
RENDERING_MODES = {
    'json': 'json',
    # Mapping of table formating options to tabulate's parameters.
    'plain': 'plain',
    'simple': 'simple',
    'fancy': 'fancy_grid'}


def json(data):
    """ Utility function to render data structure into pretty printed JSON. """
    return json_dumps(data, sort_keys=True, indent=4, separators=(',', ': '))


@click.group(invoke_without_command=True)
@click_log.init(logger)
@click_log.simple_verbosity_option(
    default='INFO', metavar='LEVEL',
    help='Either CRITICAL, ERROR, WARNING, INFO or DEBUG. Defaults to INFO.')
@click.option(
    '-m', '--manager', type=click.Choice(pool()),
    help="Restrict sub-command to one package manager. Defaults to all.")
@click.option(
    '-o', '--output-format', type=click.Choice(RENDERING_MODES),
    default='fancy', help="Rendering mode of the output. Defaults to fancy.")
@click.version_option(__version__)
@click.pass_context
def cli(ctx, manager, output_format):
    """ CLI for multi-package manager upgrades. """
    level = click_log.get_level()
    try:
        level_to_name = logging._levelToName
    # Fallback to pre-Python 3.4 internals.
    except AttributeError:
        level_to_name = logging._levelNames
    level_name = level_to_name.get(level, level)
    logger.debug('Verbosity set to {}.'.format(level_name))

    # Print help screen and exit if no sub-commands provided.
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        ctx.exit()

    # Filters out the list of considered managers depending on user choices.
    target_managers = {manager: pool()[manager]} if manager else pool()

    # Silent all log message in JSON rendering mode unless it's at debug level.
    rendering = RENDERING_MODES[output_format]
    if rendering == 'json' and level_name != 'DEBUG':
        click_log.set_level(logging.CRITICAL * 2)

    # Load up global options to the context.
    ctx.obj = {
        'target_managers': target_managers,
        'rendering': rendering}


@cli.command(short_help='List supported package managers and their location.')
@click.pass_context
def managers(ctx):
    """ List all supported package managers and their presence on the system.
    """
    target_managers = ctx.obj['target_managers']
    rendering = ctx.obj['rendering']

    # Machine-friendly data rendering.
    if rendering == 'json':
        fields = [
            'name', 'id', 'supported', 'cli_path', 'exists', 'executable',
            'version_string', 'fresh', 'available']
        # JSON mode use echo to output data because the logger is disabled.
        click.echo(json({
            manager_id: {fid: getattr(manager, fid) for fid in fields}
            for manager_id, manager in target_managers.items()}))
        return

    # Human-friendly content rendering.
    table = []
    for manager_id, manager in target_managers.items():

        # Build up the OS column content.
        os_infos = u'✅' if manager.supported else u'❌'
        if not manager.supported:
            os_infos += "  {} only".format(', '.join(sorted([
                os_label(os_id) for os_id in manager.platforms])))

        # Build up the CLI path column content.
        cli_infos = u'✅' if manager.exists else u'❌'
        cli_infos += "  {}".format(manager.cli_path)

        # Build up the version column content.
        version_infos = ''
        if manager.executable:
            version_infos = u'✅' if manager.fresh else u'❌'
            if manager.version:
                version_infos += "  {}".format(manager.version_string)
                if not manager.fresh:
                    version_infos += " {}".format(manager.requirement)

        table.append([
            manager.name,
            manager_id,
            os_infos,
            cli_infos,
            u'✅' if manager.executable else '',
            version_infos])

    table = [[
        'Package manager', 'ID', 'Supported', 'CLI', 'Executable',
        'Version']] + sorted(table, key=itemgetter(1))
    logger.info(tabulate(table, tablefmt=rendering, headers='firstrow'))


@cli.command(short_help='Sync local package info.')
@click.pass_context
def sync(ctx):
    """ Sync local package metadata and info from external sources. """
    target_managers = ctx.obj['target_managers']

    for manager_id, manager in target_managers.items():

        # Filters-out inactive managers.
        if not manager.available:
            logger.warning('Skip unavailable {} manager.'.format(manager_id))
            continue

        manager.sync()


@cli.command(short_help='List outdated packages.')
@click.option(
    '-c', '--cli-format', type=click.Choice(CLI_FORMATS), default='plain',
    help="Format of CLI fields in JSON output. Defaults to plain.")
@click.pass_context
def outdated(ctx, cli_format):
    """ List available package upgrades and their versions for each manager.
    """
    target_managers = ctx.obj['target_managers']
    rendering = ctx.obj['rendering']

    render_cli = partial(PackageManager.render_cli, cli_format=cli_format)

    # Build-up a global list of outdated packages per manager.
    outdated = {}

    for manager_id, manager in target_managers.items():

        # Filters-out inactive managers.
        if not manager.available:
            logger.warning('Skip unavailable {} manager.'.format(manager_id))
            continue

        # Force a sync to get the freshest upgrades.
        error = None
        try:
            manager.sync()
        except CLIError as expt:
            error = expt.error
            logger.error(error)

        packages = []
        for info in manager.outdated.values():
            packages.append({
                'name': info['name'],
                'id': info['id'],
                'installed_version': info['installed_version'],
                'latest_version': info['latest_version'],
                'upgrade_cli': render_cli(manager.upgrade_cli(info['id']))})

        outdated[manager_id] = {
            'id': manager_id,
            'name': manager.name,
            'packages': packages,
            'error': error}

        # Do not include the full-upgrade CLI if we did not detect any outdated
        # package.
        if manager.outdated:
            try:
                upgrade_all_cli = manager.upgrade_all_cli()
            except NotImplementedError:
                # Fallback on mpm itself which is capable of simulating a full
                # upgrade.
                upgrade_all_cli = ['mpm', '--manager', manager_id, 'upgrade']
            outdated[manager_id]['upgrade_all_cli'] = render_cli(
                upgrade_all_cli)

    # Machine-friendly data rendering.
    if rendering == 'json':
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
    table = [[
        'Package name', 'ID', 'Manager', 'Installed version',
        'Latest version']] + sorted(table, key=sort_method)
    logger.info(tabulate(table, tablefmt=rendering, headers='firstrow'))
    # Print statistics.
    manager_stats = {
        infos['id']: len(infos['packages']) for infos in outdated.values()}
    total_outdated = sum(manager_stats.values())
    per_manager_totals = ', '.join([
        '{} from {}'.format(v, k) for k, v in sorted(manager_stats.items())])
    if per_manager_totals:
        per_manager_totals = ' ({})'.format(per_manager_totals)
    logger.info('{} outdated package{} found{}.'.format(
        total_outdated,
        's' if total_outdated > 1 else '',
        per_manager_totals))


@cli.command(short_help='Upgrade all packages.')
@click.option(
    '-d', '--dry-run', is_flag=True, default=False,
    help='Do not actually perform any upgrade, just simulate CLI calls.')
@click.pass_context
def upgrade(ctx, dry_run):
    """ Perform a full package upgrade on all available managers. """
    target_managers = ctx.obj['target_managers']

    for manager_id, manager in target_managers.items():

        # Filters-out inactive managers.
        if not manager.available:
            logger.warning('Skip unavailable {} manager.'.format(manager_id))
            continue

        logger.info(
            'Updating all outdated packages from {}...'.format(manager_id))

        try:
            output = manager.upgrade_all(dry_run=dry_run)
        except CLIError as expt:
            logger.error(expt.error)

        if output:
            logger.info(output)
