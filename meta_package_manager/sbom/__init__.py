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
"""Export the installed-package inventory as Software Bill of Materials documents.

This subpackage is the home of every SBOM-flavored writer in ``mpm``. Its
existence mirrors the optional ``[sbom-offline]`` install extra defined in
``pyproject.toml``: a default ``pip install meta-package-manager`` does not
pull ``cyclonedx-python-lib`` or ``spdx-tools``, so the format modules guard
their heavy imports with ``try/except`` and expose
``spdx_support`` / ``cyclonedx_support`` flags that callers check before
instantiating the rendering classes.

Import from the named modules directly: the format-agnostic base class and
export-format enum from :py:mod:`meta_package_manager.sbom.base`, the writers
and their support flags from :py:mod:`meta_package_manager.sbom.spdx` and
:py:mod:`meta_package_manager.sbom.cyclonedx`.
"""

from __future__ import annotations
