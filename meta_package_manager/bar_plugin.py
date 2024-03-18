#!/usr/bin/env python3
# <xbar.title>Meta Package Manager</xbar.title>
# <xbar.version>v5.16.0</xbar.version>
# <xbar.author>Kevin Deldycke</xbar.author>
# <xbar.author.github>kdeldycke</xbar.author.github>
# <xbar.desc>List outdated packages and manage upgrades.</xbar.desc>
# <xbar.dependencies>python,mpm</xbar.dependencies>
# <xbar.image>https://i.imgur.com/B5wdxIc.png</xbar.image>
# <xbar.abouturl>
#    https://kdeldycke.github.io/meta-package-manager/bar-plugin.html
# </xbar.abouturl>
# <xbar.var>
#   boolean(VAR_SUBMENU_LAYOUT=false):
#   Group packages into a sub-menu for each manager.
# </xbar.var>
# <xbar.var>
#   boolean(VAR_TABLE_RENDERING=true):
#   Aligns package names and versions in a table for easier visual parsing.
# </xbar.var>
#
# XXX Deactivate font-related options for Xbar. Default variable value does not allow
# XXX `=` character in Xbar. See: https://github.com/matryer/xbar/issues/832
# <!--xbar.var>
#   string(VAR_DEFAULT_FONT=""):
#   Default font to use for non-monospaced text.
# </xbar.var-->
# <!--xbar.var>
#   string(VAR_MONOSPACE_FONT="font=Menlo size=12"):
#   Default configuration for monospace fonts, including errors.
#   Is used for table rendering.
# </xbar.var-->
# <swiftbar.environment>
#   [
#       VAR_SUBMENU_LAYOUT: false,
#       VAR_TABLE_RENDERING: true,
#       VAR_DEFAULT_FONT: ,
#       VAR_MONOSPACE_FONT: font=Menlo size=12
#   ]
# </swiftbar.environment>
"""Xbar and SwiftBar plugin for Meta Package Manager (i.e. the :command:`mpm` CLI).

Default update cycle should be set to several hours so we have a chance to get
user's attention once a day. Higher frequency might ruin the system as all
checks are quite resource intensive, and Homebrew might hit GitHub's API calls
quota.

- `Xbar automatically bridge plugin options
  <https://xbarapp.com/docs/2021/03/14/variables-in-xbar.html>`_ between its UI
  and environment variable on script execution.

- This is `in progress for SwiftBar
  <https://github.com/swiftbar/SwiftBar/issues/160>`_.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from configparser import RawConfigParser
from enum import Enum
from functools import cached_property
from operator import itemgetter, methodcaller
from pathlib import Path
from shutil import which
from subprocess import run
from textwrap import dedent
from typing import Generator

PYTHON_MIN_VERSION = (3, 8, 0)
"""Minimal requirement is aligned to mpm."""

MPM_MIN_VERSION = (5, 0, 0)
"""Mpm v5.0.0 was the first version taking care of the complete layout rendering."""

Venv = Enum("Venv", ["PIPENV", "POETRY", "VIRTUALENV"])
"""Type of virtualenv we are capable of detecting."""


class MPMPlugin:
    """Implements the minimal code necessary to locate and call the ``mpm`` CLI on the
    system.

    Once ``mpm`` is located, we can rely on it to produce the main output of the plugin.

    The output must supports both `Xbar dialect
    <https://github.com/matryer/xbar-plugins/blob/main/CONTRIBUTING.md#plugin-api>`_
    and `SwiftBar dialect <https://github.com/swiftbar/SwiftBar#plugin-api>`_.
    """

    @staticmethod
    def getenv_str(var, default: str | None = None) -> str | None:
        """Utility to get environment variables.

        Note that all environment variables are strings. Always returns a lowered-case
        string.
        """
        value = os.environ.get(var, None)
        if value is None:
            return default
        return str(value).lower()

    @staticmethod
    def getenv_bool(var, default: bool = False) -> bool:
        """Utility to normalize boolean environment variables.

        Relies on ``configparser.RawConfigParser.BOOLEAN_STATES`` to translate strings
        into boolean. See:
        https://github.com/python/cpython/blob/89192c4/Lib/configparser.py#L597-L599
        """
        value = MPMPlugin.getenv_str(var)
        if value is None:
            return default
        return RawConfigParser.BOOLEAN_STATES[value]

    @staticmethod
    def normalize_params(
        font_string: str,
        valid_ids: set[str] | None = None,
    ) -> str:
        if valid_ids is None:
            valid_ids = {"color", "font", "size"}
        valid_params = {}
        for param in font_string.split():
            param_id, param_value = param.split("=", 1)
            if param_id in valid_ids:
                valid_params[param_id] = param_value
        return " ".join(f"{k}={v}" for k, v in valid_params.items())

    @staticmethod
    def v_to_str(version_tuple: tuple[int, ...] | None) -> str:
        """Transforms into a string a tuple of integers representing a version."""
        if not version_tuple:
            return "None"
        return ".".join(map(str, version_tuple))

    @cached_property
    def table_rendering(self) -> bool:
        """Aligns package names and versions, like a table, for easier visual parsing.

        If ``True``, will aligns all items using a fixed-width font.
        """
        return self.getenv_bool("VAR_TABLE_RENDERING", True)

    @cached_property
    def default_font(self) -> str:
        """Make it easier to change font, sizes and colors of the output."""
        return self.normalize_params(
            self.getenv_str("VAR_DEFAULT_FONT", ""),  # type: ignore
        )

    @cached_property
    def monospace_font(self) -> str:
        """Make it easier to change font, sizes and colors of the output."""
        return self.normalize_params(
            self.getenv_str("VAR_MONOSPACE_FONT", "font=Menlo size=12"),  # type: ignore
        )

    @cached_property
    def error_font(self) -> str:
        """Error font is based on monospace font."""
        return self.normalize_params(f"{self.monospace_font} color=red")

    @cached_property
    def is_swiftbar(self) -> bool:
        """SwiftBar is kind enough to tell us about its presence."""
        return self.getenv_bool("SWIFTBAR")

    @cached_property
    def all_pythons(self) -> list[str]:
        """Search for any Python on the system.

        Returns a generator of normalized and deduplicated ``Path`` to Python binaries.

        Filters out old Python interpreters.

        We first try to locate Python by respecting the environment variables as-is,
        i.e. as defined by the user. Then we return the Python interpreter used to
        execute this script.

        TODO: try to tweak the env vars to look for homebrew location etc?
        """
        collected = []
        seen = set()
        for bin_name in ("python3", "python", sys.executable):
            py_path = which(bin_name)
            if not py_path:
                continue

            normalized_path = os.path.normcase(Path(py_path).resolve())
            if normalized_path in seen:
                continue
            seen.add(normalized_path)

            process = run(
                (normalized_path, "--version"),
                capture_output=True,
                encoding="utf-8",
            )
            version_string = process.stdout.split()[1]
            python_version = tuple(map(int, version_string.split(".")))
            # Is Python too old?
            if python_version < PYTHON_MIN_VERSION:
                continue

            collected.append(normalized_path)

        return collected

    @staticmethod
    def search_venv(folder: Path) -> tuple[Venv, tuple[str, ...]] | None:
        """Search for signs of a virtual env in the provided folder.

        Returns the type of the detected venv and CLI arguments that can be used to run
        a command from the virtualenv context.

        Returns ``(None, None)`` if the folder is not a venv.
        """
        if (folder / "Pipfile").is_file():
            return Venv.PIPENV, (f"PIPENV_PIPFILE='{folder}'", "pipenv", "run", "mpm")

        if (folder / "poetry.lock").is_file():
            return Venv.POETRY, ("poetry", "run", "--directory", str(folder), "mpm")

        if (folder / "requirements.txt").is_file() or (folder / "setup.py").is_file():
            return Venv.VIRTUALENV, (
                f"VIRTUAL_ENV='{folder}'",
                "python",
                "-m",
                "meta_package_manager",
            )

        return None

    def search_mpm(self) -> Generator[tuple[str, ...], None, None]:
        """Iterare over possible CLI commands to execute ``mpm``.

        Should be able to produce the full spectrum of alternative commands we can use
        to invoke ``mpm`` over different context.

        The order in which the candidates are returned by this method is conserved by
        the ``ranked_mpm()`` method below.

        We prioritize venv-based findings first, as they're more likely to have all
        dependencies installed and sorted out. They're also our prime candidates in
        unittests.

        Then we search for system-wide installation. And finally Python modules.
        """
        # This script might be itself part of an mpm installation that was deployed in
        # a virtualenv. So walk back the whole folder tree from here in search of a
        # virtualenv.
        for folder in Path(__file__).parents:
            # Stop looking beyond Home.
            if folder == Path.home():
                continue

            venv_found = self.search_venv(folder)
            if not venv_found:
                continue

            yield venv_found[1]

        # Search for an mpm executable in the environment, be it a script or a binary.
        mpm_bin = which("mpm")
        if mpm_bin:
            yield (mpm_bin,)

        # Search for a meta_package_manager package installed in any Python found on
        # the system.
        for python_path in self.all_pythons:
            yield python_path, "-m", "meta_package_manager"

    def check_mpm(
        self, mpm_cli_args: tuple[str, ...]
    ) -> tuple[bool, bool, tuple[int, ...] | None, str | Exception | None]:
        """Test-run mpm execution and extract its version."""
        error: str | Exception | None = None
        try:
            process = run(
                # Output a color-less version just in case the script is not run in a
                # non-interactive shell, or Click/Click-Extra autodetection fails.
                (*mpm_cli_args, "--no-color", "--version"),
                capture_output=True,
                encoding="utf-8",
            )
            error = process.stderr
        except FileNotFoundError as ex:
            error = ex

        runnable = False
        version = None
        up_to_date = False
        # Is mpm runnable as-is with provided CLI arguments?
        if not process.returncode and not error:
            runnable = True
            # This regular expression is designed to extract the version number,
            # whether it is surrounded by ANSI color escape sequence or not.
            match = re.compile(
                r"""
                .+                      # Any string
                \                       # A space
                version                 # The "version" string
                \                       # A space
                [^\.]*?                 # Any minimal (non-greedy) string without a dot
                (?P<version>[0-9\.]+)   # Version composed of numbers and dots
                [^\.]*?                 # Any minimal (non-greedy) string without a dot
                $                       # End of the string
                """,
                re.VERBOSE | re.MULTILINE,
            ).search(process.stdout)
            if match:
                version_string = match.groupdict()["version"]
                version = tuple(map(int, version_string.split(".")))
                # Is mpm too old?
                if version >= MPM_MIN_VERSION:
                    up_to_date = True

        return runnable, up_to_date, version, error

    @cached_property
    def ranked_mpm(
        self,
    ) -> list[
        tuple[
            tuple[str, ...], bool, bool, tuple[int, ...] | None, str | Exception | None
        ]
    ]:
        """Rank the mpm candidates we found on the system.

        Sort them by:
        - runnability
        - up-to-date status
        - version number
        - error

        On tie, the order from ``search_mpm`` is respected.
        """
        all_mpm = (
            (mpm_candidate, self.check_mpm(mpm_candidate))
            for mpm_candidate in self.search_mpm()
        )
        return [
            (mpm_args, *mpm_status)
            for mpm_args, mpm_status in sorted(all_mpm, key=itemgetter(1), reverse=True)
        ]

    @cached_property
    def best_mpm(
        self,
    ) -> tuple[
        tuple[str, ...], bool, bool, tuple[int, ...] | None, str | Exception | None
    ]:
        return self.ranked_mpm[0]

    @staticmethod
    def pp(label: str, *args: str) -> None:
        """Print one menu-line with the Xbar/SwiftBar dialect.

        First argument is the menu-line label, separated by a pipe to all other non-
        empty parameters, themselves separated by a space.

        Skip printing of the line if label is empty.
        """
        if label.strip():
            print(
                # Do not strip the label to keep character alignements, especially in
                # table rendering and Python tracebacks.
                label,
                "|",
                *(line for line in map(methodcaller("strip"), args) if line),
                sep=" ",
            )

    @staticmethod
    def print_error_header() -> None:
        """Generic header for blocking error."""
        MPMPlugin.pp("❗️", "dropdown=false")
        print("---")

    def print_error(self, message: str | Exception, submenu: str = "") -> None:
        """Print a formatted error message line by line.

        A red, fixed-width font is used to preserve traceback and exception layout. For
        compactness, the block message is dedented and empty lines are skipped.

        Message is always casted to a string as we allow passing of exception objects
        and have them rendered.
        """
        for line in map(methodcaller("rstrip"), dedent(str(message)).splitlines()):
            if line:
                self.pp(
                    f"{submenu}{line}",
                    self.error_font,
                    "trim=false",
                    "ansi=false",
                    "emojize=false",
                    "symbolize=false" if self.is_swiftbar else "",
                )

    def print_menu(self) -> None:
        """Print the main menu."""
        mpm_args, runnable, up_to_date, _version, error = self.best_mpm
        if not runnable or not up_to_date:
            self.print_error_header()
            if error:
                self.print_error(error)
                print("---")
            action_msg = "Install" if not runnable else "Upgrade"
            min_version_str = self.v_to_str(MPM_MIN_VERSION)
            self.pp(
                f"{action_msg} mpm >= v{min_version_str}",
                f"shell={self.all_pythons[0]}",
                "param1=-m",
                "param2=pip",
                "param3=install",
                "param4=--upgrade",
                # XXX This seems broken beyond repair. No amount of workaround works.
                # See:
                # https://github.com/matryer/xbar/issues/831
                # https://github.com/swiftbar/SwiftBar/issues/308
                # Fallback to the only version that is working on SwiftBar.
                f'param5=\\"meta-package-manager>={min_version_str}\\"',
                self.error_font,
                "refresh=true",
                "terminal=true",
            )
            return

        # Force a sync of all local package databases.
        run((*mpm_args, "--verbosity", "ERROR", "sync"))

        # Fetch outdated packages from all package managers available on the system.
        # We defer all rendering to mpm itself so it can compute more intricate layouts.
        process = run(
            # We silence all errors but the CRITICAL ones. All others will be captured
            # by mpm in --plugin-output mode and rendered back into each manager
            # section.
            (*mpm_args, "--verbosity", "CRITICAL", "outdated", "--plugin-output"),
            capture_output=True,
            encoding="utf-8",
        )

        # Bail-out immediately on errors related to mpm self-execution or if mpm is
        # not able to produce any output.
        if process.stderr or not process.stdout:
            self.print_error_header()
            self.print_error(process.stderr)
            return

        # Capturing the output of mpm and re-printing it will introduce an extra
        # line returns, hence the extra rstrip() call.
        print(process.stdout.rstrip())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--search-mpm",
        action="store_true",
        help="Locate all mpm on the system and sort them by best candidates.",
    )
    args = parser.parse_args()

    plugin = MPMPlugin()

    if args.search_mpm:
        for mpm_args, runnable, up_to_date, version, error in plugin.ranked_mpm:
            print(
                f"{' '.join(mpm_args)} | runnable: {runnable} | "
                f"up to date: {up_to_date} | version: {version} | error: {error!r}"
            )

    else:
        plugin.print_menu()
