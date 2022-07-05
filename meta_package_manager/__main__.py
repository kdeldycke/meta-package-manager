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

"""Allow the module to be run as a CLI. I.e.:

.. code-block:: shell-session

    $ python -m meta_package_manager

Removes empty string and current working directory from the first entry of
`sys.path`, if present to avoid using current directory
in subcommands when invoked as `python -m meta_package_manager <command>`.
"""

from __future__ import annotations

import os
import sys

if sys.path[0] in ("", os.getcwd()):
    sys.path.pop(0)


if __name__ == "__main__":

    from meta_package_manager.cli import mpm

    # Execute the CLI but force its name to not let Click defaults to:
    # "python -m meta_package_manager".
    mpm(prog_name=mpm.name)
