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
"""Introspection utilities to produce feature inventory of all managers."""

from __future__ import annotations

from extra_platforms import (
    ALL_WINDOWS,
    BSD_WITHOUT_MACOS,
    LINUX_LIKE,
    MACOS,
    UNIX_WITHOUT_MACOS,
    Group,
)

TYPE_CHECKING = False
if TYPE_CHECKING:
    from extra_platforms import Platform


MAIN_PLATFORMS: tuple[Group | Platform, ...] = (
    BSD_WITHOUT_MACOS.copy(id="bsd", name="BSD"),
    LINUX_LIKE.copy(id="linux", name="Linux", icon="🐧"),
    MACOS,
    UNIX_WITHOUT_MACOS.copy(
        id="unix",
        name="Unix",
        members=tuple(UNIX_WITHOUT_MACOS - BSD_WITHOUT_MACOS - LINUX_LIKE),
    ),
    ALL_WINDOWS.copy(id="windows", name="Windows"),
)
"""Top-level classification of platforms.

This is the local reference used to classify the execution targets of ``mpm``.

Each entry of this list will have its own dedicated column in the matrix. This list is
manually maintained with tweaked IDs and names to minimize the matrix verbosity and
make it readable both in CLI and documentation.

The order of this list determine the order of the resulting columns.
"""
