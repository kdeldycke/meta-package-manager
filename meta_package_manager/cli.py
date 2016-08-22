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

import click
import click_log

from . import (
    __version__,
    logger,
    PACKAGE_MANAGERS
)


@click.group(invoke_without_command=True)
@click_log.init(logger)
@click_log.simple_verbosity_option(default='INFO', metavar='LEVEL')
@click.version_option(__version__)
@click.pass_context
def cli(ctx):
    """ CLI for multi-package manager updates and upgrades. """
    # Print help screen and exit if no sub-commands provided.
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        ctx.exit()
    # Load up global options to the context.
    ctx.obj = {}


@cli.command(short_help='List supported package managers and their location.')
@click.pass_context
def managers(ctx):
    """ List all supported package managers and their presence on the system.
    """
    for klass in PACKAGE_MANAGERS:
        manager = klass()
        logger.info('{}: {} ({}).'.format(
            manager.name,
            'Active' if manager.active else 'Not found',
            manager.cli))


@cli.command(short_help='List available updates.')
@click.pass_context
def list(ctx):
    """ List available package updates.
    """
    logger.error('Not implemented yet.')
