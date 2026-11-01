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
"""The pURLs of the SBOM writers.

Each package carries two pURLs. {func}`package_purl` ties the package to its manager,
the manager ID as its type: both documents key the package by it, as the CycloneDX
`bom-ref`, the SPDX ID and the coordinate an advisory maps back to.
{func}`registered_purl` names the package under its registered type, the pURL other
tools read: both documents give it as the pURL of the package, and fall back to the
first one without it.

cyclonedx-python-lib serializes a pURL only from a `PackageURL` of packageurl-python,
through `to_string()`, which normalizes the parts its own way: it lowercases the npm
name the npm type keeps. {func}`cyclonedx_purl` makes it serialize the string `mpm`
rendered. packageurl-python comes with the `[sbom-offline]` extra: the writers import
this module among their guarded imports, so without it they are disabled like without
`cyclonedx-python-lib`.
"""

from __future__ import annotations

from extra_platforms import current_platform
from packageurl import PackageURL

from ..package import PURL_TYPES, manager_purl, purl_parts, purl_quote, render_purl
from ..specifier import BREW_DEFAULT_TAPS, PURL_MAP

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable

    from ..package import Package


DISTRO_PURL_TYPES = frozenset(("alpm", "apk", "deb", "rpm"))
"""The registered pURL types whose namespace is the vendor of a distribution.

{func}`registered_purl` fills it with the ID of the running distribution, as its
`os-release` file states it.
"""

MANAGERS_WITHOUT_REGISTERED_PURL = frozenset(("cpan", "dkp-pacman"))
"""The managers whose packages a registered pURL type would misname.

The `cpan` manager names a Perl module, where the `cpan` type names the distribution
shipping it. `dkp-pacman` installs the packages of devkitPro, which no distribution
vendors.
"""


def package_purl(package: Package) -> str:
    """The pURL tying `package` to its manager, the manager ID as its type.

    {func}`~meta_package_manager.package.manager_purl` renders it, which splits the ID
    so a scoped npm package or a tap-qualified formula carries its namespace. A known
    architecture becomes the `arch` qualifier.
    """
    version = package.installed_version
    purl = manager_purl(
        package.manager_id, package.id, str(version) if version else None
    )
    if package.arch:
        purl += f"?arch={purl_quote(package.arch)}"
    return purl


def registered_type(manager_id: str) -> str | None:
    """The registered pURL type of the packages of `manager_id`, or `None`.

    The one type of {data}`~meta_package_manager.package.PURL_TYPES` that
    {data}`~meta_package_manager.specifier.PURL_MAP` ties to the manager, or the
    manager ID itself when it is registered.
    """
    if manager_id in MANAGERS_WITHOUT_REGISTERED_PURL:
        return None
    types = {
        purl_type
        for purl_type, manager_ids in PURL_MAP.items()
        if purl_type in PURL_TYPES and manager_id in (manager_ids or ())
    }
    if manager_id in PURL_TYPES:
        types.add(manager_id)
    return types.pop() if len(types) == 1 else None


def distro_vendor() -> str | None:
    """The ID of the running Linux distribution, or `None` outside one."""
    distro_id = current_platform().info().get("distro_id")
    return distro_id if isinstance(distro_id, str) and distro_id else None


def registered_purl(package: Package) -> str | None:
    """The pURL of `package` under its registered type, or `None` without a valid one.

    Takes the type {func}`registered_type` names, with the namespace and the name
    {func}`~meta_package_manager.package.purl_parts` splits from the ID, but for these
    types:

    - A type of {data}`DISTRO_PURL_TYPES` takes the whole ID as the name, and the ID of
      the running distribution as the namespace.
    - `brew` puts a cask of the `cask` manager under the `homebrew/cask` tap.
    - `vscode-extension` splits the ID at its first dot, between the publisher and the
      name.
    - `vcpkg` moves the triplet of the ID and the port version of the version into the
      `triplet` and `port_version` qualifiers.

    A known architecture becomes the `arch` qualifier. Returns `None` when the parts
    break a rule of the type, like a `julia` package without its UUID.
    """
    purl_type = registered_type(package.manager_id)
    if purl_type is None:
        return None
    namespace, name = purl_parts(package.id)
    version = str(package.installed_version) if package.installed_version else None
    qualifiers = {"arch": package.arch} if package.arch else {}
    if purl_type in DISTRO_PURL_TYPES:
        namespace, name = distro_vendor(), package.id
    elif purl_type == "brew" and package.manager_id == "cask" and not namespace:
        namespace = next(
            tap for tap, owner in BREW_DEFAULT_TAPS.items() if owner == "cask"
        )
    elif purl_type == "vscode-extension":
        namespace, _, name = package.id.partition(".")
    elif purl_type == "vcpkg":
        name, _, triplet = package.id.partition(":")
        if triplet:
            qualifiers["triplet"] = triplet
        if version:
            version, _, port_version = version.partition("#")
            if port_version:
                qualifiers["port_version"] = port_version
    try:
        return render_purl(purl_type, namespace, name, version, qualifiers)
    except ValueError:
        return None


class _RenderedPackageURL(PackageURL):
    """A `PackageURL` serializing to the string `mpm` rendered."""

    rendered: str

    def to_string(self, encode: bool | None = True) -> str:
        return self.rendered


def cyclonedx_purl(purl: str) -> PackageURL | None:
    """Wrap `purl` for cyclonedx-python-lib.

    Returns `None` when packageurl-python cannot read it.
    """
    try:
        parsed = PackageURL.from_string(purl)
    except ValueError:
        return None
    wrapped = _RenderedPackageURL(*parsed)
    wrapped.rendered = purl
    return wrapped


def normalized_purls(purls: Iterable[str]) -> tuple[str, ...]:
    """Render each pURL string the way packageurl-python normalizes it."""
    return tuple(PackageURL.from_string(purl).to_string() for purl in purls)
