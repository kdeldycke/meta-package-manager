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

""" Expose package-wide elements. """

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals
)

import logging
import os
import sys


__version__ = '1.11.1'


PY2 = sys.version_info[0] == 2
PY3 = sys.version_info[0] == 3


# We only support macOS for now.
if sys.platform != 'darwin':
    raise RuntimeError(
        "{} platform is not supported. Only macOS is.".format(sys.platform))


logger = logging.getLogger(__name__)


# OS X does not put /usr/local/bin or /opt/local/bin in the PATH for GUI apps.
# For some package managers this is a problem. Additioanlly Homebrew and
# Macports are using different pathes.  So, to make sure we can always get to
# the necessary binaries, we overload the path.  Current preference order would
# equate to Homebrew, Macports, then System.
os.environ['PATH'] = ':'.join(['/usr/local/bin',
                               '/usr/local/sbin',
                               '/opt/local/bin',
                               '/opt/local/sbin',
                               os.environ.get('PATH', '')])
