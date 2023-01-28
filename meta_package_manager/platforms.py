# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
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

"""``mpm``'s platform introspection utilities."""

import dataclasses
from typing import Tuple

from click_extra.platforms import ALL_LINUX, ALL_WINDOWS, BSD_WITHOUT_MACOS
from click_extra.platforms import MACOS as MACOS_PLATFORM
from click_extra.platforms import UNIX as ALL_UNIX
from click_extra.platforms import WSL2, Group

BSD: Group = dataclasses.replace(BSD_WITHOUT_MACOS, name="BSD", icon="🅱️")
LINUX: Group = Group("linux", "Linux", tuple((*ALL_LINUX.platforms, WSL2)), icon="🐧")
MACOS: Group = Group("macos", "macOS", (MACOS_PLATFORM,), icon="🍎")
# Catch all for all Unix-like platforms not already covered by BSD, LINUX
# and MACOS groups above.
UNIX: Group = Group(
    "unix",
    "Unix",
    tuple(
            p
            for p in ALL_UNIX.platforms
            if p not in BSD.platforms + LINUX.platforms + MACOS.platforms
    ),
    icon="`>_`",
)
WINDOWS: Group = dataclasses.replace(ALL_WINDOWS, name="Windows", icon="🪟")
"""Define comprehensive platform groups to minimize the operation matrix verbosity."""


PLATFORM_GROUPS: Tuple[Group, ...] = tuple(
    sorted((BSD, LINUX, MACOS, UNIX, WINDOWS), key=lambda g: g.name.lower())
)
"""Sorted list of platform groups that will have their own dedicated column in the matrix."""
