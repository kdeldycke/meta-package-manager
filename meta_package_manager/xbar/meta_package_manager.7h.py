#!/usr/bin/env python3
# <xbar.title>Meta Package Manager</xbar.title>
# <xbar.version>v4.13.1</xbar.version>
# <xbar.author>Kevin Deldycke</xbar.author>
# <xbar.author.github>kdeldycke</xbar.author.github>
# <xbar.desc>List outdated packages and manage upgrades.</xbar.desc>
# <xbar.dependencies>python,mpm</xbar.dependencies>
# <xbar.image>https://i.imgur.com/CiQpQ42.png</xbar.image>
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

import json
import os
import re
import subprocess
from configparser import RawConfigParser


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


MPM_MIN_VERSION = (4, 2, 0)
"""Mpm v4.2.0 was the first supporting the new xbar plugin parameter format."""


is_swift_bar = getenv_bool("SWIFTBAR")
"""SwiftBar is kind enough to warn us of its presence."""


dark_mode = (
    getenv_str("OS_APPEARANCE", "light") == "dark"
    if is_swift_bar
    else getenv_bool("XBARDarkMode")
)
"""Detect dark mode."""


def fix_environment():
    """Tweak environment variable to find non-default system-wide binaries.

    macOS does not put ``/usr/local/bin`` or ``/opt/local/bin`` in the ``PATH`` for GUI
    apps. For some package managers this is a problem. Additioanlly Homebrew and
    Macports are using different pathes. So, to make sure we can always get to the
    necessary binaries, we overload the path. Current preference order would equate to
    Homebrew, Macports, then system.
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


def pp(*args):
    """Print the item line.

    First argument is the label, separated with a pipe to all other non-empty
    parameters.
    """
    line = args[0]
    params = " ".join(p for p in args[1:] if p)
    if params:
        line += f" | {params}"
    print(line)


def print_error_header():
    """Generic header for blocking error."""
    pp("❗️", "dropdown=false")
    print("---")


def print_error(message, submenu=""):
    """Print a formatted error line by line.

    A red, fixed-width font is used to preserve traceback and exception layout.
    """
    # Cast to string as we might directly pass exceptions for rendering.
    for line in str(message).strip().splitlines():
        pp(
            f"{submenu}{line}",
            FONTS["error"],
            "trim=false",
            "ansi=false",
            "emojize=false",
            "symbolize=false" if is_swift_bar else "",
        )


def print_cli_item(*args):
    """Print two CLI entries:

    * one that is silent
    * a second one that is the exact copy of the above but forces the execution
      by the way of a visible terminal
    """
    pp(*args, "terminal=false")
    pp(*args, "terminal=true", "alternate=true")


def print_upgrade_all_item(manager, submenu=""):
    """Print the menu entry to upgrade all outdated package of a manager."""
    if manager.get("upgrade_all_cli"):
        if SUBMENU_LAYOUT:
            print("-----")
        print_cli_item(
            f"{submenu}🆙 Upgrade all {manager['id']} packages",
            # Retro-compatibility with xbar-style pipe-separated parameters.
            # See: https://github.com/swiftbar/SwiftBar/issues/306
            manager["upgrade_all_cli"].replace(" | ", " "),
            FONTS["normal"],
            "refresh=true",
        )


def print_menu():
    """Print menu structure using the common parameters shared by Xbar and SwiftBar.

    See:
    - https://github.com/matryer/xbar-plugins/blob/main/CONTRIBUTING.md#plugin-api
    - https://github.com/swiftbar/SwiftBar#plugin-api
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
        print_error_header()
        print_error(error)
        print("---")
        action_msg = "Install" if not mpm_installed else "Upgrade"
        min_version_str = ".".join(map(str, MPM_MIN_VERSION))
        pp(
            f"{action_msg} mpm CLI >= v{min_version_str}",
            "shell=python3",
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
    subprocess.run(("mpm", "--verbosity", "ERROR", "sync"))

    # Fetch outdated package from all package manager available on the system.
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

    # Let mpm set the order in which managers will be sorted.
    managers = json.loads(process.stdout).values()

    # Print menu bar icon with number of available upgrades.
    total_outdated = sum(len(m["packages"]) for m in managers)
    total_errors = sum(len(m.get("errors", [])) for m in managers)
    pp(
        (f"🎁↑{total_outdated}" if total_outdated else "📦✓")
        + (f" ⚠️{total_errors}" if total_errors else ""),
        "dropdown=false",
    )

    # Prefix for section content.
    submenu = "--" if SUBMENU_LAYOUT else ""

    # String used to separate the left and right columns.
    col_sep = "  " if TABLE_RENDERING else " "
    up_sep = " → "

    # Compute global length constant.
    global_outdated_len = max(len(str(len(m["packages"]))) for m in managers)
    package_str = "package"
    right_col_len = global_outdated_len + len(package_str) + 1  # +1 for plural

    # Global maximum length of labels.
    global_len_name = max(len(p["name"]) for m in managers for p in m["packages"])
    global_len_manager = max(len(m["id"]) for m in managers)
    global_len_left = max((global_len_manager, global_len_name))
    global_len_installed = max(
        len(p["installed_version"]) for m in managers for p in m["packages"]
    )
    global_len_latest = max(
        len(p["latest_version"]) for m in managers for p in m["packages"]
    )
    global_len_right = max(
        [
            right_col_len,
            global_len_installed + len(up_sep) + global_len_latest,
        ]
    )

    for manager in managers:
        plural = "s" if len(manager["packages"]) > 1 else ""
        package_label = f"{package_str}{plural}"

        name_max_len = installed_max_len = latest_max_len = 0

        if SUBMENU_LAYOUT:
            error = "⚠️ " if manager.get("errors", None) else ""

        if TABLE_RENDERING:

            if SUBMENU_LAYOUT:
                # Re-define layout maximum dimensions for each manager.
                left_col_len = global_len_manager
                if manager["packages"]:
                    name_max_len = max(len(p["name"]) for p in manager["packages"])
                    installed_max_len = max(
                        len(p["installed_version"]) for p in manager["packages"]
                    )
                    latest_max_len = max(
                        len(p["latest_version"]) for p in manager["packages"]
                    )

            else:
                # Layout constraints are defined across all managers.
                left_col_len = name_max_len = global_len_left
                installed_max_len = global_len_installed
                latest_max_len = global_len_latest
                right_col_len = global_len_right

            outdated_label = (
                f"{len(manager['packages']):>{global_outdated_len}} {package_label:<8}"
            )

            header = f"{manager['id']:<{left_col_len}}{col_sep}{outdated_label:>{right_col_len}}"

        # Variable-width / non-table / non-monospaced rendering.
        else:
            header = (
                f"{len(manager['packages'])} outdated {manager['name']} {package_label}"
            )

        # Print section separator before printing the manager header.
        print("---")
        # Print section header.
        pp(f"{error}{header}", FONTS["summary"])

        # Print a menu entry for each outdated packages.
        for pkg_info in manager["packages"]:
            print_cli_item(
                f"{submenu}{pkg_info['name']:<{name_max_len}}"
                + col_sep
                + f"{pkg_info['installed_version']:>{installed_max_len}}"
                + up_sep
                + f"{pkg_info['latest_version']:<{latest_max_len}}",
                # Retro-compatibility with xbar-style pipe-separated parameters.
                # See: https://github.com/swiftbar/SwiftBar/issues/306
                pkg_info["upgrade_cli"].replace(" | ", " "),
                FONTS["package"],
                "refresh=true",
            )

        print_upgrade_all_item(manager, submenu)

        for error_msg in manager.get("errors", []):
            print("-----" if SUBMENU_LAYOUT else "---")
            print_error(error_msg, submenu)


if __name__ == "__main__":
    fix_environment()
    print_menu()
