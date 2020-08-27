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

""" Utilities to load parameters and options from a configuration file. """

import click
import tomlkit
from pathlib import Path
from . import logger, CLI_NAME


def config_structure():
    """Returns the supported configuration structure.

    Derives TOML structure from CLI definition.
    """
    # Imported here to avoid circular imports.
    from .cli import cli

    # Global, top-level options shared by all subcommands are placed under the
    # cli name's section.
    # TODO: exclude version option.
    # TODO: take particular attention to boolean flag options.
    config = {CLI_NAME: {p.name for p in cli.params}}

    # Subcommand-specific options.
    for cmd_id, cmd in cli.commands.items():
        config[cmd_id] = {p.name for p in cmd.params}

    return config


def read_config(custom_conf=None):
    """ Loads a configuration files and returns recognized options.

    If no config file provided, defaults to the ``config.toml`` file found in a
    folder depending on the OS:
    * macOS & Linux:
        ~/.mpm/
    * Windows XP:
        C:\\Documents and Settings\\<user>\\Local Settings\\Application Data\\mpm\\
    * Windows 7:
        C:\\Users\\<user>\\AppData\\Roaming\\mpm\\

    As per: https://click.palletsprojects.com/en/7.x/api/#click.get_app_dir

    Invalid parameters are ignored and log messages are emitted.
    """
    # The recognized configuration extracted from the file.
    valid_config = {}

    # Get configuration from provided file.
    if custom_conf:
        cfg_filepath = Path(custom_conf).resolve()
    # Get configuration from default location.
    else:
        cfg_filepath = Path(
            click.get_app_dir(CLI_NAME, force_posix=True), "config.toml"
        ).resolve()

    # Check config file. Issues with non-default config file are fatal.
    if not cfg_filepath.exists():
        if custom_conf:
            logger.fatal(f"Configuration not found at {cfg_filepath}")
            raise FileNotFoundError
        else:
            logger.warning(f"Configuration not found at {cfg_filepath}")
            return valid_config
    if not cfg_filepath.is_file():
        logger.fatal(f"Configuration {cfg_filepath} is not a file.")
        raise FileNotFoundError

    # Parse TOML content.
    logger.info(f"Load configuration from {cfg_filepath}")
    doc = tomlkit.parse(cfg_filepath.read_bytes())

    # Filters-out configuration file's content against the reference structure and
    # only keep recognized options.
    structure = config_structure()

    for section, options in doc.items():

        # Ignore unrecognized section.
        if section not in structure:
            logger.warning(f"Ignore [{section}] section.")
            continue

        # Dive into section and look at options.
        valid_options = {}
        for opt_id, opt_value in options.items():

            # Ignore unrecognized option.
            if opt_id not in structure[section]:
                logger.warning(f"Ignore [{section}].{opt_id} option.")
                continue

            # Keep option.
            valid_options[opt_id] = opt_value

        valid_config[section] = valid_options

    return valid_config
