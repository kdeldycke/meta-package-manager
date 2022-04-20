#!/usr/bin/env python3
# <xbar.title>Meta Package Manager</xbar.title>
# <xbar.version>v5.0.0</xbar.version>
# <xbar.author>Kevin Deldycke</xbar.author>
# <xbar.author.github>kdeldycke</xbar.author.github>
# <xbar.desc>List outdated packages and manage upgrades.</xbar.desc>
# <xbar.dependencies>python,mpm</xbar.dependencies>
# <xbar.image>https://i.imgur.com/B5wdxIc.png</xbar.image>
# <xbar.abouturl>https://github.com/kdeldycke/meta-package-manager</xbar.abouturl>
# <xbar.var>boolean(VAR_SUBMENU_LAYOUT=false): Group packages into manager sub-menus.</xbar.var>
# <xbar.var>boolean(VAR_TABLE_RENDERING=false): Aligns package names and versions in a table for easier visual parsing.</xbar.var>
# <swiftbar.environment>['VAR_SUBMENU_LAYOUT': false, 'VAR_TABLE_RENDERING': false]</swiftbar.environment>

"""Xbar and SwiftBar plugin for Meta Package Manager (i.e. the :command:`mpm` CLI).

Default update cycle is set to 7 hours so we have a chance to get user's
attention once a day. Higher frequency might ruin the system as all checks are
quite resource intensive, and Homebrew might hit GitHub's API calls quota.

Minimal requirement is macOS Catalina (10.15) for both Xbar and SwiftBar.
Catalina deprecates Python 2.x, and ships with Python 3.7.3. So this plugin is
required to work with Python 3.7.3 or newer.

- Xbar automaticcaly bridge plugin options between its UI and environment
variable on script execution. See:
https://xbarapp.com/docs/2021/03/14/variables-in-xbar.html

- This is in progress for SwiftBar at:
https://github.com/swiftbar/SwiftBar/issues/160
"""

import os
import re
import subprocess
import sys
from configparser import RawConfigParser
from shutil import which
from unittest.mock import patch

if sys.version_info >= (3, 8):
    from functools import cached_property
else:
    cached_property = property


def getenv_str(var, default=None):
    """Utility to get environment variables.

    Note that all environment variables are strings. Always returns a lowered-case
    string.
    """
    value = os.environ.get(var, None)
    if value is None:
        return default
    return str(value).lower()


def getenv_bool(var, default=False):
    """Utility to normalize boolean environment variables.

    Relies on ``configparser.RawConfigParser.BOOLEAN_STATES`` to translate strings into boolean. See:
    https://github.com/python/cpython/blob/89192c46da7b984811ff3bd648f8e827e4ef053c/Lib/configparser.py#L597-L599
    """
    value = getenv_str(var)
    if value is None:
        return default
    return RawConfigParser.BOOLEAN_STATES[value]


SUBMENU_LAYOUT = getenv_bool("VAR_SUBMENU_LAYOUT", False)
""" Group packages into manager sub-menus.

If ``True``, will replace the default flat layout with an alternative structure
where actions are grouped into submenus, one for each manager.
"""


TABLE_RENDERING = getenv_bool("VAR_TABLE_RENDERING", True)
""" Aligns package names and versions, like a table, for easier visual parsing.

If ``True``, will aligns all items using a fixed-width font.
"""

# Make it easier to change font, sizes and colors of the output
MONOSPACE = "font=Menlo size=12"
FONTS = {
    "normal": "",  # Use default system font
    "summary": "",  # Package summary
    "package": "",  # Indiviual packages
    "error": f"{MONOSPACE} color=red",  # Errors
}
# Use a monospaced font on table-like rendering.
if TABLE_RENDERING:
    FONTS.update(dict.fromkeys(["summary", "package"], MONOSPACE))


MPM_MIN_VERSION = (5, 0, 0)
"""Mpm v5.0.0 was the first version taking care of the layout rendering."""


IS_SWIFTBAR = getenv_bool("SWIFTBAR")
"""SwiftBar is kind enough to tell us about its presence."""


DARK_MODE = (
    getenv_str("OS_APPEARANCE", "light") == "dark"
    if IS_SWIFTBAR
    else getenv_bool("XBARDarkMode")
)
"""Detect dark mode."""


class MPMPlugin:
    """Implements the minimal code necessary to locate and call the ``mpm`` CLI on the system.

    Once ``mpm`` is located, we can rely on it to produce the main output of the plugin.

    The output must supports both Xbar and SwiftBar:
        - https://github.com/matryer/xbar-plugins/blob/main/CONTRIBUTING.md#plugin-api
        - https://github.com/swiftbar/SwiftBar#plugin-api
    """

    @staticmethod
    def extended_environment():
        """Returns a tweaked environment extending global path to find non-default system-
        wide binaries.

        macOS does not put ``/usr/local/bin`` or ``/opt/local/bin`` in the ``PATH`` for GUI
        apps. For some package managers this is a problem. Additioanlly Homebrew and
        Macports are using different pathes. So, to make sure we can always get to the
        necessary binaries, we overload the path. Current preference order would equate to
        Homebrew, Macports, then system.
        """
        # Cast to dict to make a copy and prevent modification of the global environment.
        env_copy = dict(os.environ)
        env_copy["PATH"] = ":".join(
            (
                # Homebrew Apple silicon.
                "/opt/homebrew/bin",
                "/opt/homebrew/sbin",
                # Homebrew Intel.
                "/usr/local/bin",
                "/usr/local/sbin",
                # Macports.
                "/opt/local/bin",
                "/opt/local/sbin",
                # System.
                os.environ.get("PATH", ""),
            )
        )
        return env_copy

    @staticmethod
    def locate_bin(*bin_names):
        """Find the location of an executable binary on the system.

        Provides as many binary names as you need, the first one found will be returned. Both plain name and full path
        are supported.
        """
        for name in bin_names:
            path = which(name)
            if path:
                return path

    @cached_property
    def python_path(self):
        """ Returns the system's Python binary path.

        This plugin being run from Python, we have the one called by Xbar/SwiftBar to fallback
        to (i.e. ``sys.executable``). But before that, we attempt to locate it by respecting the environment
        variables.
        """
        return self.locate_bin("python", "python3", sys.executable)

    @cached_property
    def mpm_exec(self):
        """Search for mpm execution alternatives, either direct ``mpm`` call or as an executable Python module."""
        mpm_exec = (self.locate_bin("mpm"),)
        if not mpm_exec:
            mpm_exec = (self.python_path, "-m", "meta_package_manager")
        return mpm_exec

    @staticmethod
    def pp(*args):
        """Print one menu-line with the Xbar/SwiftBar dialect.

        First argument is the menu-line label, separated by a pipe to all other non-empty parameters, themselves separated by a space.
        """
        line = []
        for param in args:
            if param:
                if len(line) == 1:
                    line.append("|")
                line.append(param)
        print(*line, sep=' ')

    @staticmethod
    def print_error_header():
        """Generic header for blocking error."""
        MPMPlugin.pp("❗️", "dropdown=false")
        print("---")

    @staticmethod
    def print_error(message, submenu=""):
        """Print a formatted error line by line.

        A red, fixed-width font is used to preserve traceback and exception layout.
        """
        # Cast to string as we might directly pass exceptions for rendering.
        for line in str(message).strip().splitlines():
            MPMPlugin.pp(
                f"{submenu}{line}",
                FONTS["error"],
                "trim=false",
                "ansi=false",
                "emojize=false",
                "symbolize=false" if IS_SWIFTBAR else "",
            )

    def print_menu(self):
        """Print the main menu."""
        # Test mpm execution.
        code = None
        error = None
        try:
            process = subprocess.run(
                (*self.mpm_exec, "--version"), capture_output=True, encoding="utf-8"
            )
            code = process.returncode
            error = process.stderr
        except FileNotFoundError as ex:
            error = ex

        mpm_installed = False
        mpm_up_to_date = False
        # Is mpm CLI installed on the system?
        if not code and not error:
            mpm_installed = True
            # Is mpm too old?
            version_string = (
                re.compile(r".*\s+(?P<version>[0-9\.]+)$", re.MULTILINE)
                .search(process.stdout)
                .groupdict()["version"]
            )
            mpm_version = tuple(map(int, version_string.split(".")))
            if mpm_version >= MPM_MIN_VERSION:
                mpm_up_to_date = True

        if not mpm_installed or not mpm_up_to_date:
            self.print_error_header()
            self.print_error(error)
            print("---")
            action_msg = "Install" if not mpm_installed else "Upgrade"
            min_version_str = ".".join(map(str, MPM_MIN_VERSION))
            self.pp(
                f"{action_msg} mpm >= v{min_version_str}",
                f"shell={self.python_path}",
                "param1=-m",
                "param2=pip",
                "param3=install",
                "param4=--upgrade",
                # XXX This seems broken beyond repair. No amount of workaround works. See:
                # https://github.com/matryer/xbar/issues/831
                # https://github.com/swiftbar/SwiftBar/issues/308
                # Fallback to the only version that is working on SwiftBar.
                f'param5=\\"meta-package-manager>={min_version_str}\\"',
                FONTS["error"],
                "refresh=true",
                "terminal=true",
            )
            return

        # Force a sync of all local package databases.
        subprocess.run((*self.mpm_exec, "--verbosity", "ERROR", "sync"))

        # Fetch outdated packages from all package managers available on the system.
        # We defer all rendering to mpm itself so it can compute more intricate layouts.
        process = subprocess.run(
            (
                *self.mpm_exec,
                "--verbosity",
                "ERROR",
                "outdated",
                "--plugin",
                "swiftbar" if IS_SWIFTBAR else "xbar",
                "--plugin-submenu-layout" if SUBMENU_LAYOUT else "--plugin-flat-layout",
                "--plugin-aligned-columns" if TABLE_RENDERING else "--plugin-no-alignment",
                "--plugin-dark-mode" if DARK_MODE else "--plugin-light-mode",
            ),
            capture_output=True,
            encoding="utf-8",
        )

        # Bail-out immediately on errors related to mpm self-execution or if mpm is
        # not able to produce any output.
        if process.stderr or not process.stdout:
            self.print_error_header()
            self.print_error(process.stderr)
        else:
            # Capturing the output of mpm and re-printing it will introduce an extra line returns, hence the extra rstrip() call.
            print(process.stdout.rstrip())


if __name__ == "__main__":

    # Wrap plugin execution with our custom environment variables to avoid environment leaks.
    with patch.dict("os.environ", MPMPlugin.extended_environment()):
        MPMPlugin().print_menu()
