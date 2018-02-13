# -*- coding: utf-8 -*-
#
# Copyright (c) 2016-2017 Kevin Deldycke <kevin@deldycke.com>
#                         and contributors.
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

from subprocess import PIPE, Popen

from .platform import is_windows


# Default encoding for all platforms
ENCODING = 'utf-8'

if is_windows():
    ENCODING = 'latin-1'


def run(*args):
    """Run a shell command, return error code, output and error message."""
    assert isinstance(args, tuple)
    try:
        process = Popen(args, stdout=PIPE, stderr=PIPE)
    except OSError:
        return None, None, "`{}` executable not found.".format(args[0])
    output, error = process.communicate()
    return (
        process.returncode,
        output.decode(ENCODING) if output else None,
        error.decode(ENCODING) if error else None)
