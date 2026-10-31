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
"""The pURLs of the SBOM writers, built with packageurl-python.

An SBOM records each package under the pURL that packageurl-python renders, with its
normalization, where the rest of `mpm` reads and writes pURL strings itself (see
{func}`~meta_package_manager.package.parse_purl`). packageurl-python comes with the
`[sbom-offline]` extra: the writers import this module among their guarded imports,
so without it they are disabled like without `cyclonedx-python-lib`.
"""

from __future__ import annotations

from packageurl import PackageURL

from ..package import purl_parts

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable

    from ..package import Package


def package_purl(package: Package) -> PackageURL:
    """The pURL of `package`, its manager ID as the type.

    {func}`~meta_package_manager.package.purl_parts` splits the ID, so a scoped npm
    package or a tap-qualified formula carries its namespace the way the pURL
    specification expects. A known architecture becomes the `arch` qualifier.
    """
    namespace, name = purl_parts(package.id)
    return PackageURL(
        type=package.manager_id,
        namespace=namespace,
        name=name,
        version=str(package.installed_version),
        qualifiers={"arch": package.arch} if package.arch else {},
    )


def normalized_purls(purls: Iterable[str]) -> tuple[str, ...]:
    """Render each pURL string the way packageurl-python normalizes it."""
    return tuple(PackageURL.from_string(purl).to_string() for purl in purls)
