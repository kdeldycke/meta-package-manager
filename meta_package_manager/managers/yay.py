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

import re

from click_extra.platform import LINUX

from .pacman import Pacman


class Yay(Pacman):
    """yay has the commands equivalent to pacman."""

    requirement = "11.0.0"

    pre_args = ("--noconfirm",)

    version_regex = r".*yay\s+v(?P<version>\S+)"
    r"""Search version right after the ``yay `` string.

    .. code-block:: shell-session

        ► yay --version
        yay v11.1.2 - libalpm v13.0.1
    """
