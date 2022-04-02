#!/usr/bin/env python3
# <xbar.title>Meta Package Manager</xbar.title>
# <xbar.version>v4.11.0</xbar.version>
# <xbar.author>Kevin Deldycke</xbar.author>
# <xbar.author.github>kdeldycke</xbar.author.github>
# <xbar.desc>List outdated packages and manage upgrades.</xbar.desc>
# <xbar.dependencies>python,mpm</xbar.dependencies>
# <xbar.image>https://i.imgur.com/CiQpQ42.png</xbar.image>
# <xbar.abouturl>https://github.com/kdeldycke/meta-package-manager</xbar.abouturl>
# <xbar.var>boolean(VAR_SUBMENU_LAYOUT=false): Group packages into manager sub-menus.</xbar.var>

"""
xbar plugin for Meta Package Manager (a.k.a. the :command:`mpm` CLI).

Default update cycle is set to 7 hours so we have a chance to get user's
attention once a day. Higher frequency might ruin the system as all checks are
quite resource intensive, and Homebrew might hit GitHub's API calls quota.

Minimal xbar requirement is macOS Catalina (10.15), which deprecates Python
2.x, and ships with Python 3.7.3. So this plugin is required to work with
Python 3.7.3 or newer.
"""

import json
import os
import re
import subprocess
from operator import itemgetter

SUBMENU_LAYOUT = bool(
    os.environ.get("VAR_SUBMENU_LAYOUT", False)
    in {True, 1, "True", "true", "1", "y", "yes", "Yes"}
)
""" Define the rendering mode of outdated packages list.

If ``True``, will replace the default flat layout with an alternative structure
where all upgrade actions are grouped into submenus, one for each manager.

xbar automaticcaly bridge that option between its UI and environment variable
on script execution.
See: https://xbarapp.com/docs/2021/03/14/variables-in-xbar.html
"""


# Make it easier to change font, sizes and colors of the output
# See https://github.com/matryer/xbar#writing-plugins for details
# An alternate "good looking" font is "font=NotoMono size=13" (not installed
# on macOS by default though) that matches the system font quite well.
FONTS = {
    "normal": "",  # Use default system font
    "summary": "",  # Package summary
    "package": "",  # Indiviual packages
    "error": "color=red | font=Menlo | size=12",  # Errors
}
# Use a monospaced font when using submenus.
if SUBMENU_LAYOUT:
    FONTS["summary"] = "font=Menlo | size=12"


# mpm v4.2.0 was the first supporting the new xbar plugin parameter format.
MPM_MIN_VERSION = (4, 2, 0)


def fix_environment():
    """Tweak environment variable to find non-default system-wide binaries.

    macOS does not put ``/usr/local/bin`` or ``/opt/local/bin`` in the ``PATH``
    for GUI apps. For some package managers this is a problem. Additioanlly
    Homebrew and Macports are using different pathes. So, to make sure we can
    always get to the necessary binaries, we overload the path. Current
    preference order would equate to Homebrew, Macports, then system.
    """
    os.environ["PATH"] = ":".join(
        (
            "/usr/local/bin",
            "/usr/local/sbin",
            "/opt/local/bin",
            "/opt/local/sbin",
            os.environ.get("PATH", ""),
        )
    )


def pp(params):
    """Print all parameters separated by a pipe. Ignore empty items."""
    print(" | ".join(p for p in params if p))


def print_error_header():
    """Generic header for blockng error."""
    pp(("❌", "dropdown=false"))
    print("---")


def print_error(message, submenu=""):
    """Print a formatted error line by line.

    A red, fixed-width font is used to preserve traceback and exception layout.
    """
    for line in message.strip().splitlines():
        pp([f"{submenu}{line}", FONTS["error"], "trim=false", "emojize=false"])


def print_cli_item(item):
    """Print two CLI entries:
    * one that is silent
    * a second one that is the exact copy of the above but forces the execution
      by the way of a visible terminal
    """
    pp(item + ["terminal=false"])
    pp(item + ["terminal=true", "alternate=true"])


def print_package_items(packages, submenu=""):
    """Print a menu entry for each outdated packages available for upgrade."""
    for pkg_info in packages:
        print_cli_item(
            [
                f"{submenu}{pkg_info['name']} "
                f"{pkg_info['installed_version']} → {pkg_info['latest_version']}",
                pkg_info["upgrade_cli"],
                "refresh=true",
                FONTS["package"],
                "emojize=false",
            ]
        )


def print_upgrade_all_item(manager, submenu=""):
    """Print the menu entry to upgrade all outdated package of a manager."""
    if manager.get("upgrade_all_cli"):
        if SUBMENU_LAYOUT:
            print("-----")
        print_cli_item(
            [
                f"{submenu}Upgrade all",
                manager["upgrade_all_cli"],
                "refresh=true",
                FONTS["normal"],
            ]
        )


def print_menu():
    """Print menu structure using xbar's plugin API.

    See: https://github.com/matryer/xbar#plugin-api
    """
    # Search for generic mpm CLI on system.
    code = None
    error = None
    try:
        process = subprocess.run(
            ("mpm", "--version"), capture_output=True, encoding="utf-8"
        )
        code = process.returncode
        error = process.stderr
    except FileNotFoundError as excpt:
        error = excpt

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
        print_error_header()
        print_error(error)
        print("---")
        action_msg = "Install" if not mpm_installed else "Upgrade"
        min_version_str = ".".join(map(str, MPM_MIN_VERSION))
        pp(
            [
                f"{action_msg} mpm CLI >= v{min_version_str}",
                "shell=python3",
                "param1=-m",
                "param2=pip",
                "param3=install",
                "param4=--upgrade",
                f'param5="meta-package-manager>={min_version_str}"',
                "terminal=true",
                "refresh=true",
                FONTS["error"],
            ]
        )
        return

    # Force a sync of all local package databases.
    subprocess.run(("mpm", "--verbosity", "ERROR", "sync"))

    # Fetch outdated package form all package manager available on the system.
    process = subprocess.run(
        (
            "mpm",
            "--verbosity",
            "ERROR",
            "--output-format",
            "json",
            "outdated",
            "--cli-format",
            "xbar",
        ),
        capture_output=True,
        encoding="utf-8",
    )

    # Bail-out immediately on errors related to mpm self-execution or if mpm is
    # not able to produce any output.
    if process.stderr or not process.stdout:
        print_error_header()
        print_error(process.stderr)
        return

    # Sort outdated packages by manager's name.
    managers = sorted(json.loads(process.stdout).values(), key=itemgetter("name"))

    # Print menu bar icon with number of available upgrades.
    total_outdated = sum(len(m["packages"]) for m in managers)
    total_errors = sum(len(m.get("errors", [])) for m in managers)
    pp(
        [
            "↑{}{}".format(
                total_outdated, f" ⚠️{total_errors}" if total_errors else ""
            ),
            "dropdown=false",
        ]
    )

    # Print a full detailed section for each manager.
    submenu = "--" if SUBMENU_LAYOUT else ""

    if SUBMENU_LAYOUT:
        # Compute maximal manager's name length.
        label_max_length = max(len(m["name"]) for m in managers)
        max_outdated = max(len(m["packages"]) for m in managers)
        print("---")

    for manager in managers:
        package_label = "package{}".format("s" if len(manager["packages"]) > 1 else "")

        if SUBMENU_LAYOUT:
            # Non-flat layout use a compact table-like rendering of manager
            # summary.
            pp(
                [
                    "{error}{0:<{max_length}} {1:>{max_outdated}} {2:<8}".format(
                        manager["name"] + ":",
                        len(manager["packages"]),
                        package_label,
                        error="⚠️ " if manager.get("errors", None) else "",
                        max_length=label_max_length + 1,
                        max_outdated=len(str(max_outdated)),
                    ),
                    FONTS["summary"],
                    "emojize=false",
                ]
            )
        else:
            print("---")
            pp(
                [
                    f"{len(manager['packages'])} outdated {manager['name']} {package_label}",
                    FONTS["summary"],
                    "emojize=false",
                ]
            )

        print_package_items(manager["packages"], submenu)

        print_upgrade_all_item(manager, submenu)

        for error_msg in manager.get("errors", []):
            print("-----" if SUBMENU_LAYOUT else "---")
            print_error(error_msg, submenu)


if __name__ == "__main__":
    fix_environment()
    print_menu()
