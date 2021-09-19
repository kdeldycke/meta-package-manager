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
from click.core import ParameterSource

from . import CLI_NAME, logger

DEFAULT_CONF_NAME = "config.toml"


# List of unsupported options we're going to ignore.
IGNORED_OPTIONS = [
    # --version is not a configurable option.
    "version",
    # -C/--config option cannot be used to link to another file.
    "config",
]


class ConfigurationFileError(Exception):
    """Base class for all exceptions related to configuration file."""

    pass


def default_conf_path():
    """Returns default location of the configuration file.

    Location depends on OS (see `Click documentation
    <https://click.palletsprojects.com/en/8.0.x/api/#click.get_app_dir>`_):

        * macOS & Linux: ``~/.mpm/config.toml``

        * Windows: ``C:\\Users\\<user>\\AppData\\Roaming\\mpm\\config.toml``
    """
    return Path(
        click.get_app_dir(CLI_NAME, force_posix=True), DEFAULT_CONF_NAME
    ).resolve()


def conf_structure():
    """Returns the supported configuration structure.

    Derives TOML structure from CLI definition.

    Sections are dicts. All options have their defaults value to None.
    """
    # Imported here to avoid circular imports.
    from .cli import cli

    # Global, top-level options shared by all subcommands are placed under the
    # cli name's section.
    conf = {
        CLI_NAME: {p.name: None for p in cli.params if p.name not in IGNORED_OPTIONS}
    }

    # Subcommand-specific options.
    for cmd_id, cmd in cli.commands.items():
        cmd_options = {
            p.name: None for p in cmd.params if p.name not in IGNORED_OPTIONS
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

    return clean_conf


def load_conf(ctx, param, config_file):

    # Display a message for the user to make him aware he is using a non-default configuration file.
    explicit_conf = ctx.get_parameter_source("config") in (
        ParameterSource.COMMANDLINE,
        ParameterSource.ENVIRONMENT,
        ParameterSource.PROMPT,
    )
    # Always print a message if the user explicitly set the configuration location.
    # We can't use logger.info yet because the default have not been loaded yet and the logger is stuck to its default WARNING level.
    if explicit_conf:
        click.echo(f"Load configuration at {config_file}", err=True)
    else:
        if not config_file:
            config_file = default_conf_path()
        logger.debug(f"Load configuration at {config_file}")

    # Fetch option from configuration file.
    conf = {}
    try:
        # Re-fetch config file location
        conf = read_conf(config_file)
    except ConfigurationFileError as excpt:
        # Exit the CLI if the user-provided config file is bad.
        if explicit_conf:
            logger.fatal(excpt)
            ctx.exit(2)
        else:
            logger.debug(excpt)
            logger.debug("Ignore configuration file.")

    logger.debug(f"Loaded configuration: {conf}")

    # Merge user config to the context default_map. See:
    # https://click.palletsprojects.com/en/8.0.x/commands/#context-defaults
    # This allow user's config to only overrides defaults. Values sets from direct
    # command line calls, environment variables or interactive prompts takes precedence
    # over any parameters from the config file.
    if ctx.default_map is None:
        ctx.default_map = dict()
    ctx.default_map.update(conf.get(CLI_NAME, {}))

    return config_file
