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

""" This is the last place in which we support Python 2.7 to allow BitBar
plugin to be tested out in our CI workflow.
"""

try:
    # Python 3.
    from importlib.machinery import SourceFileLoader
    from pathlib import Path

    PY = 3
except ImportError:
    # Python 2.
    import imp
    from os import path

    PY = 2


# Manually import BitBar plugin source code as a module, because of its non
# Python-compliant filename with a double extension made the first dot
# interpreted as a submodule.
if PY == 2:
    here = path.dirname(path.abspath(__file__))
    bitbar_plugin = path.join(here, "meta_package_manager.7h.py")
    imp.load_source(__name__, bitbar_plugin)
else:
    SourceFileLoader(
        __name__,
        str(Path(__file__).parent.joinpath("meta_package_manager.7h.py").resolve()),
    ).load_module()
