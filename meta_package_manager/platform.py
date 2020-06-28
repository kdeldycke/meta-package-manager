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

""" Helpers and utilities to identify and handle platform idiosyncracies. """

import sys

from boltons.dictutils import FrozenDict

from . import logger

LINUX = "linux"
""" Constant used to identify OSes of the Linux family. """


MACOS = "macos"
""" Constant used to identify OSes of the macOS family. """


WINDOWS = "windows"
""" Constant used to identify OSes of the Windows family. """


def is_linux():
    """ Return `True` only if current platform is of the Linux family. """
    return sys.platform.startswith("linux")


def is_macos():
    """ Return `True` only if current platform is of the macOS family. """
    return sys.platform == "darwin"


def is_windows():
    """ Return `True` only if current platform is of the Windows family. """
    return sys.platform in ["win32", "cygwin"]


# Map OS IDs to evaluation function and OS labels.
OS_DEFINITIONS = FrozenDict(
    {
        LINUX: ("Linux", is_linux()),
        MACOS: ("macOS", is_macos()),
        WINDOWS: ("Windows", is_windows()),
    }
)


# Generare sets of recognized IDs and labels.
ALL_OS_LABELS = frozenset([label for label, _ in OS_DEFINITIONS.values()])


def os_label(os_id):
    """ Return platform label for user-friendly output. """
    return OS_DEFINITIONS[os_id][0]


logger.debug(f"Raw platform ID: {sys.platform}.")


def current_os():
    """ Return a 2-items `tuple` with ID and label of current OS. """
    for os_id, (os_name, os_flag) in OS_DEFINITIONS.items():
        if os_flag is True:
            return os_id, os_name
    raise SystemError("Unrecognized {} platform.".format(sys.platform))


CURRENT_OS_ID, CURRENT_OS_LABEL = current_os()
