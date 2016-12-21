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
MACOS = 'darwin'
LINUX = 'linux2'
WINDOWS = 'win32'


# Map platform IDs to OS labels.
OS_LABELS = {
    MACOS: 'macOS',
    LINUX: 'Linux',
    WINDOWS: 'Windows'}


def current_platform():
    """ Return ID of current platform. """
    platform_id = sys.platform
    logger.debug("Current platform: {} (ID: {}).".format(
        platform_label(platform_id), platform_id))
    return platform_id


def platform_label(platform_id):
    """ Return platform label for user-friendly output. """
    return OS_LABELS.get(platform_id, 'unrecognized')
