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

from __future__ import annotations

import sys
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

""" Import manually the *Bar plugin source code as a module.

This is necessary because of its non Python-compliant filename. The double
``.7h.py`` extension made the first dot interpreted as a submodule.
"""
loader = SourceFileLoader(
    __name__,
    str(Path(__file__).parent.joinpath("meta_package_manager.7h.py").resolve()),
)
spec = spec_from_loader(loader.name, loader)
module = module_from_spec(spec)  # type: ignore
loader.exec_module(module)
sys.modules[__name__] = module
