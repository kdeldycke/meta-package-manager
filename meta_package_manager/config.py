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

from pathlib import Path

import click
import tomlkit

from . import CLI_NAME, logger

DEFAULT_CONFIG_FILE = Path(
    click.get_app_dir(CLI_NAME, force_posix=True), "config.toml"
).resolve()
"""
Default configuration file.

Location depends on OS (see `Click documentation
<https://click.palletsprojects.com/en/8.0.x/api/#click.get_app_dir>`_):

    * macOS & Linux: ``~/.mpm/config.toml``

    * Windows: ``C:\\Users\\<user>\\AppData\\Roaming\\mpm\\config.toml``
"""


class ConfigurationFileError(Exception):
    """Base class for all exceptions related to configuration file."""

    pass


def config_structure():
    """Returns the supported configuration structure.

    Derives TOML structure from CLI definition.
    """
    # Imported here to avoid circular imports.
    from .cli import cli

    # List of unsupported options we're going to ignore.
    ignored_options = [
        # --version is not a configurable option.
        "version",
        # -C/--config option cannot be used to link to another file.
        "config",
    ]

    # Global, top-level options shared by all subcommands are placed under the
    # cli name's section.
    config = {CLI_NAME: {p.name for p in cli.params if p.name not in ignored_options}}

    # Subcommand-specific options.
    for cmd_id, cmd in cli.commands.items():
        cmd_options = {p.name for p in cmd.params if p.name not in ignored_options}
        if cmd_options:
            config[cmd_id] = cmd_options

    return config


def read_config(cfg_filepath):
    """Loads a configuration files and returns recognized options and their values.

    Invalid parameters are ignored and log messages are emitted.
    """
    # The recognized configuration extracted from the file.
    valid_config = {}

    # Check config file.
    if not cfg_filepath.exists():
        raise ConfigurationFileError(f"Configuration not found at {cfg_filepath}")
    if not cfg_filepath.is_file():
        raise ConfigurationFileError(f"Configuration {cfg_filepath} is not a file.")

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

        if valid_options:
            valid_config[section] = valid_options
        else:
            logger.warning(f"Ignore empty [{section}] section.")

    return valid_config
