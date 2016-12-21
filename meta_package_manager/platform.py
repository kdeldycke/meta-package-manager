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

""" Helpers and utilities to handle platform idiosyncracies. """

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals
)

import sys

from . import logger

# Python version constants.
PY_VERSION = sys.version_info
PY2 = PY_VERSION[0] == 2
PY3 = PY_VERSION[0] == 3


# OS identification constants.
MACOS = 'macos'
LINUX = 'linux'
WINDOWS = 'windows'


def is_linux():
    """ Return True only if current platform is Linux. """
    return sys.platform.startswith('linux')


def is_macos():
    """ Return True only if current platform is macOS. """
    return sys.platform == 'darwin'


def is_windows():
    """ Return True only if current platform is Windows. """
    return sys.platform in ['win32', 'cygwin']


# Map OS IDs to evaluation function and OS labels.
OS_DEFINITIONS = {
    MACOS: ('macOS', is_macos),
    LINUX: ('Linux', is_linux),
    WINDOWS: ('Windows', is_windows)}


def current_os():
    """ Return ID and label of current OS. """
    platform_id = sys.platform
    logger.debug("Raw platform ID: {}.".format(platform_id))
    for os_id, (os_label, eval_func) in OS_DEFINITIONS.items():
        if eval_func():
            return os_id, os_label
    raise SystemError("Unrecognized {} platform.".format(platform_id))


def os_label(os_id):
    """ Return platform label for user-friendly output. """
    return OS_DEFINITIONS[os_id][0]
