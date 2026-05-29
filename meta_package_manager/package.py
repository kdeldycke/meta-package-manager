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
"""Manager-agnostic :py:class:`meta_package_manager.package.Package` data model.

Defines the lightweight representation of a package (ID, name, installed and latest
versions, architecture) that every manager operation yields, plus
:py:func:`meta_package_manager.package.packages_asdict` to serialize a subset of its
fields for output.

Kept deliberately free of manager logic, so it can be imported without pulling in the
manager engine (:py:mod:`meta_package_manager.manager`).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import cached_property

from packageurl import PackageURL

from .version import parse_version

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from .version import TokenizedString


@dataclass
class Package:
    """Lightweight representation of a package and its metadata."""

    id: str
    """ID is required and is the primary key used by the manager."""

    manager_id: str
    """Handy to backtrack whose manager this package belongs to.

    The manager ID is good enough and allows for no coupling with the parent manager
    object.
    """

    name: str | None = None
    """Optional human-readable display name. Falls back to ``id`` in output rendering,
    so only set this when the manager provides a name that differs from the package ID.
    """

    description: str | None = None

    installed_version: TokenizedString | str | None = None
    latest_version: TokenizedString | str | None = None
    """Installed and latest versions are optional: they're not always provided by the
    package manager.

    ``installed_version`` and ``latest_version`` are allowed to temporarily be strings
    between ``__init__`` and ``__post_init__``. Once they reach the later, they're
    parsed and normalized into either ``TokenizedString`` or `None`. They can't be
    strings beyond that point, i.e. after the Package instance has been fully
    instantiated. We don't know how to declare this transient state with type hints,
    so we're just going to allow string type.
    """

    arch: str | None = None

    def __post_init__(self) -> None:
        # Make sure version strings are parsed into proper objects.
        self.installed_version = parse_version(self.installed_version)  # type: ignore[arg-type]
        self.latest_version = parse_version(self.latest_version)  # type: ignore[arg-type]

    @cached_property
    def purl(self) -> PackageURL:
        """Returns the package's pURL object."""
        qualifiers = {}
        if self.arch:
            qualifiers["arch"] = self.arch
        return PackageURL(
            type=self.manager_id,
            name=self.id,
            version=str(self.installed_version),
            qualifiers=qualifiers,
        )


def packages_asdict(packages: Iterator[Package], keep_fields: tuple[str, ...]):
    """Returns a list of packages casted to a ``dict`` with only a subset of its
    fields."""
    return ({k: v for k, v in asdict(p).items() if k in keep_fields} for p in packages)
