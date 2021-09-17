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
import tomli
from boltons.iterutils import remap

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


def conf_structure():
    """Returns the supported configuration structure.

    Derives TOML structure from CLI definition.

    Sections are dicts. All options have their defaults value to None.
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
    conf = {
        CLI_NAME: {p.name: None for p in cli.params if p.name not in ignored_options}
    }

    # Subcommand-specific options.
    for cmd_id, cmd in cli.commands.items():
        cmd_options = {
            p.name: None for p in cmd.params if p.name not in ignored_options
        }
        if cmd_options:
            conf[CLI_NAME][cmd_id] = cmd_options

    return conf


def read_conf(conf_filepath):
    """Loads a configuration files and only returns recognized options and their values.

    Invalid parameters are ignored.
    """
    # Check conf file.
    if not conf_filepath.exists():
        raise ConfigurationFileError(f"Configuration not found at {conf_filepath}")
    if not conf_filepath.is_file():
        raise ConfigurationFileError(f"Configuration {conf_filepath} is not a file.")

    # Parse TOML content.
    logger.info(f"Load configuration from {conf_filepath}")
    user_conf = tomli.loads(conf_filepath.read_text())

    # Merge configuration file's content into the canonical reference structure, but
    # ignore all unrecognized options.

    def recursive_update(a, b):
        """Like standard ``dict.update()``, but recursive so sub-dict gets updated.

        Ignore elements present in ``b`` but not in ``a``.
        """
        for k, v in b.items():
            if isinstance(v, dict) and isinstance(a.get(k), dict):
                a[k] = recursive_update(a[k], v)
            # Ignore elements unregistered in the canonical structure.
            elif k in a:
                a[k] = b[k]
        return a

    valid_conf = recursive_update(conf_structure(), user_conf)

    # Clean-up blank values left-over by the canonical reference structure.

    def visit(path, key, value):
        """Skip None values and empty dicts."""
        if value is None:
            return False
        if isinstance(value, dict) and not len(value):
            return False
        return True

    clean_conf = remap(valid_conf, visit=visit)

    logger.debug(f"Configuration loaded: {clean_conf}")

    return clean_conf
