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
"""Typed surface used by managers to expose richer per-package metadata to
:py:mod:`meta_package_manager.sbom`.

The :py:class:`Package` model in :py:mod:`meta_package_manager.package` is the
inventory plane and stays minimal (id, name, version): it backs every command
including ``mpm installed``, ``mpm dump``, and ``mpm sbom --minimal``.

This module defines the dataclasses populated only when ``mpm sbom`` runs in
``--bundled`` mode. Managers override
:py:meth:`meta_package_manager.manager.PackageManager.package_metadata_batch`
to fill in whatever their underlying CLI or on-disk layout exposes. Renderers
in :py:mod:`meta_package_manager.sbom` consume the result and translate it
into SPDX 2.3 and CycloneDX 1.7 constructs.

Every field is optional. A manager that can only report a homepage fills the
``homepage`` slot and leaves the rest at their defaults; the renderers gate
each field on its presence and silently omit unknown data rather than
synthesizing placeholders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

TYPE_CHECKING = False
if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path

    from packageurl import PackageURL


class DependencyScope(str, Enum):
    """Maps loosely onto SPDX ``RelationshipType`` variants.

    Renderers translate these into ``RUNTIME_DEPENDENCY_OF``,
    ``BUILD_DEPENDENCY_OF``, etc. CycloneDX collapses everything to its
    flat ``dependencies`` graph.
    """

    RUNTIME = "runtime"
    BUILD = "build"
    DEV = "dev"
    OPTIONAL = "optional"
    TEST = "test"
    RECOMMENDED = "recommended"


class ChecksumAlgorithm(str, Enum):
    """Subset of algorithms shared by SPDX and CycloneDX schemas."""

    MD5 = "MD5"
    SHA1 = "SHA1"
    SHA256 = "SHA256"
    SHA512 = "SHA512"
    SHA3_256 = "SHA3-256"
    SHA3_512 = "SHA3-512"
    BLAKE2B_256 = "BLAKE2b-256"
    BLAKE2B_512 = "BLAKE2b-512"


@dataclass(frozen=True)
class Checksum:
    """A single ``(algorithm, value)`` pair."""

    algorithm: ChecksumAlgorithm
    value: str


@dataclass(frozen=True)
class Supplier:
    """Distributor of the package.

    Distinct from the originator: the supplier is whoever served the bits
    (Homebrew, Debian, PyPI), the originator is the upstream author.
    """

    name: str
    url: str | None = None


@dataclass(frozen=True)
class Originator:
    """Upstream author or organization that produced the package."""

    name: str
    email: str | None = None
    is_organization: bool = False


@dataclass(frozen=True)
class Dependency:
    """A single edge in the package's declared dependency graph.

    ``target_id`` is the dependency's manager-native identifier (e.g.
    ``openssl@3`` for Homebrew). Renderers match it against the inventory's
    installed packages to decide whether to emit a relationship.
    """

    target_id: str
    scope: DependencyScope = DependencyScope.RUNTIME
    version_constraint: str | None = None


@dataclass(frozen=True)
class FileEntry:
    """An installed file shipped by the package.

    Only populated for managers that can cheaply enumerate file contents and
    hashes (dpkg ``.md5sums``, pip ``RECORD``). Omitted otherwise; the
    renderer leaves ``filesAnalyzed=False`` on the SPDX Package.
    """

    path: str
    sha256: str | None = None
    sha1: str | None = None
    md5: str | None = None


@dataclass
class PackageMetadata:
    """Maximalist metadata collected for a single installed package.

    All fields are optional. ``extras`` is the escape hatch for manager-
    native fields that don't fit the portable model: a Homebrew tap, a pip
    classifier list, an apt ``Section``. Renderers consult known keys and
    surface the rest as CycloneDX ``properties``.
    """

    download_url: str | None = None
    homepage: str | None = None
    vcs_url: str | None = None
    issue_tracker_url: str | None = None
    distribution_url: str | None = None

    license_declared: str | None = None
    license_concluded: str | None = None
    copyright_text: str | None = None

    supplier: Supplier | None = None
    originator: Originator | None = None

    description: str | None = None
    summary: str | None = None
    cpe: str | None = None

    dependencies: tuple[Dependency, ...] = ()
    checksums: tuple[Checksum, ...] = ()
    files: tuple[FileEntry, ...] = ()
    files_analyzed: bool = False

    install_date: datetime | None = None
    build_date: datetime | None = None
    release_date: datetime | None = None

    external_sbom_path: Path | None = None
    """Path to an on-disk upstream SBOM document for this package.

    Brew formulae installed with ``HOMEBREW_SBOM=1`` write a per-formula
    SPDX 2.3 file at ``<prefix>/sbom.spdx.json``. The Homebrew extractor
    sets this so the renderer can merge the upstream document into the
    aggregate output (or attach it by reference).
    """

    extra_purls: tuple[PackageURL, ...] = ()
    """Additional purls when the manager identifies the same package
    through multiple coordinate systems (multi-arch, multi-origin)."""

    extras: dict[str, object] = field(default_factory=dict)
    """Manager-native metadata that does not map cleanly to SPDX or
    CycloneDX. Renderers may expose entries as CycloneDX ``properties``.
    """

    def is_empty(self) -> bool:
        """``True`` if the extractor produced no meaningful metadata.

        Used by the renderers to short-circuit field-by-field gating and by
        the CLI to log which managers contributed enrichment.
        """
        return (
            not self.download_url
            and not self.homepage
            and not self.vcs_url
            and not self.issue_tracker_url
            and not self.distribution_url
            and not self.license_declared
            and not self.license_concluded
            and not self.copyright_text
            and self.supplier is None
            and self.originator is None
            and not self.description
            and not self.summary
            and not self.cpe
            and not self.dependencies
            and not self.checksums
            and not self.files
            and self.install_date is None
            and self.build_date is None
            and self.release_date is None
            and self.external_sbom_path is None
            and not self.extra_purls
            and not self.extras
        )


EMPTY_METADATA = PackageMetadata()
"""Sentinel returned by the default no-op extractor on the base
:py:class:`PackageManager`. Renderers treat ``EMPTY_METADATA`` exactly like
``--minimal`` mode for the package: no enrichment, no placeholders."""
