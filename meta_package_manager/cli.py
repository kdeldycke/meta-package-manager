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
from operator import itemgetter

import click
import click_log
from tabulate import tabulate

from . import __version__, logger
from .managers import pool


# Mapping of table formatiing options to tabulate's parameters.
TABLE_FORMAT = {
    'plain': 'plain',
    'simple': 'simple',
    'fancy': 'fancy_grid'}


@click.group(invoke_without_command=True)
@click_log.init(logger)
@click_log.simple_verbosity_option(
    default='INFO', metavar='LEVEL',
    help='Either CRITICAL, ERROR, WARNING, INFO or DEBUG. Defaults to INFO.')
@click.option(
    '-t', '--table-format', type=click.Choice(TABLE_FORMAT), default='fancy',
    help="Rendering format of tables. Defaults to fancy.")
@click.version_option(__version__)
@click.pass_context
def cli(ctx, table_format):
    """ CLI for multi-package manager updates and upgrades. """
    level = click_log.get_level()
    logger.debug('Verbosity set to {}.'.format(
        logging._levelNames.get(level, level)))

    # Print help screen and exit if no sub-commands provided.
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        ctx.exit()

    # Load up global options to the context.
    ctx.obj = {
        'table_format': TABLE_FORMAT[table_format]}


@cli.command(short_help='List supported package managers and their location.')
@click.pass_context
def managers(ctx):
    """ List all supported package managers and their presence on the system.
    """
    table = []

    # Filters-out inactive managers.
    for manager_id, manager in pool().items():
        table.append([
            manager.name,
            manager_id,
            manager.version,
            u'✅' if manager.available else '',
            manager.cli_path if manager.available else ''])

    table = [[
        'Package manager', 'ID', 'Version', 'Available', 'Location']] + sorted(
            table, key=itemgetter(1))

    logger.info(tabulate(
        table, tablefmt=ctx.obj['table_format'], headers='firstrow'))


@cli.command(short_help='Sync local package info.')
@click.pass_context
def sync(ctx):
    """ Sync local package metadata and info from external sources. """
    for manager_id, manager in pool().items():

        # Filters-out inactive managers.
        if not manager.available:
            logger.warning('Skip unavailable {} manager.'.format(manager_id))
            continue

        manager.sync()


@cli.command(short_help='List available updates.')
@click.pass_context
def outdated(ctx):
    """ List available package updates and their versions for each manager. """
    table = []

    for manager_id, manager in pool().items():

        # Filters-out inactive managers.
        if not manager.available:
            logger.warning('Skip unavailable {} manager.'.format(manager_id))
            continue

        manager.sync()

        if manager.error:
            logger.error(manager.error)

        for pkg_info in manager.updates:
            table.append([
                pkg_info['name'],
                pkg_info['name'],
                manager_id,
                pkg_info['installed_version'],
                pkg_info['latest_version'],
            ])

    # Sort table by package ID, then manager ID.
    table = [[
        'Package name', 'ID', 'Manager', 'Installed version',
        'Latest version']] + sorted(table, key=itemgetter(1, 2))
    logger.info(tabulate(
        table, tablefmt=ctx.obj['table_format'], headers='firstrow'))

    # Print statistics.
    manager_stats = {
        manager_id: len(manager.updates)
        for manager_id, manager in pool().items() if manager.updates}
    total_outdated = sum(manager_stats.values())
    per_manager_totals = ', '.join([
        '{} from {}'.format(v, k) for k, v in sorted(manager_stats.items())])
    if per_manager_totals:
        per_manager_totals = ' ({})'.format(per_manager_totals)
    logger.info('{} outdated package{} found{}.'.format(
        total_outdated,
        's' if total_outdated > 1 else '',
        per_manager_totals))


@cli.command(short_help='Update all packages.')
@click.pass_context
def update(ctx):
    """ Perform a full package update on all available managers. """
    for manager_id, manager in pool().items():

        # Filters-out inactive managers.
        if not manager.available:
            logger.warning('Skip unavailable {} manager.'.format(manager_id))
            continue

        logger.info(
            'Updating all outdated packages from {}...'.format(manager_id))
        output = manager.update_all()
        logger.info(output)
