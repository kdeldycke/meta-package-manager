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
"""CycloneDX 1.7 writer.

Heavy ``cyclonedx-python-lib`` imports are guarded behind a ``try/except``
block; ``cyclonedx_support`` reports whether the
:py:class:`CycloneDX` class can actually be used.

The license-normalization helper is shared with :py:mod:`.spdx` and is
imported from there rather than duplicated: SPDX license expressions are
the lingua franca CycloneDX builds on, so the dependency direction is
intentional and acyclic.
"""

from __future__ import annotations

import logging

from packageurl import PackageURL

from .. import __version__
from ..package import (
    EMPTY_METADATA,
    ChecksumAlgorithm,
    PackageMetadata,
)
from .base import SBOM, ExportFormat
from .spdx import _parse_license_expression

cyclonedx_support = True
try:
    from cyclonedx.model import (
        ExternalReference,
        ExternalReferenceType,
        HashAlgorithm,
        HashType,
        Property,
        XsUri,
    )
    from cyclonedx.model.bom import Bom
    from cyclonedx.model.component import Component, ComponentType
    from cyclonedx.model.contact import OrganizationalContact, OrganizationalEntity
    from cyclonedx.model.license import (
        DisjunctiveLicense,
        LicenseExpression,
        LicenseExpressionDetails,
    )
    from cyclonedx.model.lifecycle import LifecyclePhase, PredefinedLifecycle
    from cyclonedx.model.vulnerability import (
        BomTarget,
        Vulnerability as CDXVulnerability,
        VulnerabilityAdvisory,
        VulnerabilityRating,
        VulnerabilityReference,
        VulnerabilitySeverity,
        VulnerabilitySource,
    )
    from cyclonedx.output import make_outputter
    from cyclonedx.output.json import JsonV1Dot7
    from cyclonedx.schema import OutputFormat, SchemaVersion
except ImportError:
    cyclonedx_support = False
    logging.getLogger("meta_package_manager").debug(
        "CycloneDX support disabled: install meta-package-manager[sbom-offline] to enable it.",
    )

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Any

    from ..manager import PackageManager
    from ..package import Package


# ``Any``-valued map to avoid cascading mypy errors at every call site: the
# values are typed ``HashAlgorithm`` instances but the conditional
# ``try/except`` import above hides that fact from the type checker.
_CYCLONEDX_HASH_MAP: dict[str, Any] = {}
_CYCLONEDX_SEVERITY_MAP: dict[str, Any] = {}
if cyclonedx_support:
    _CYCLONEDX_HASH_MAP = {
        ChecksumAlgorithm.MD5.value: HashAlgorithm.MD5,
        ChecksumAlgorithm.SHA1.value: HashAlgorithm.SHA_1,
        ChecksumAlgorithm.SHA256.value: HashAlgorithm.SHA_256,
        ChecksumAlgorithm.SHA512.value: HashAlgorithm.SHA_512,
        ChecksumAlgorithm.SHA3_256.value: HashAlgorithm.SHA3_256,
        ChecksumAlgorithm.SHA3_512.value: HashAlgorithm.SHA3_512,
        ChecksumAlgorithm.BLAKE2B_256.value: HashAlgorithm.BLAKE2B_256,
        ChecksumAlgorithm.BLAKE2B_512.value: HashAlgorithm.BLAKE2B_512,
    }
    # Maps the coarse severity labels produced by
    # meta_package_manager.sbom.vulnerabilities onto CycloneDX's enum.
    _CYCLONEDX_SEVERITY_MAP = {
        "low": VulnerabilitySeverity.LOW,
        "medium": VulnerabilitySeverity.MEDIUM,
        "high": VulnerabilitySeverity.HIGH,
        "critical": VulnerabilitySeverity.CRITICAL,
    }


class CycloneDX(SBOM):
    """Generates a CycloneDX document from a list of packages.

    `CycloneDX 1.7 specifications <https://cyclonedx.org/docs/1.7>`_.
    """

    document: Bom
    component_index: dict[tuple[str, str], Component]
    pending_dependencies: list[tuple[Component, str, str]]

    def init_doc(self) -> None:
        """
        `CycloneDX document metadata specifications
        <https://cyclonedx.org/docs/1.7/json/#metadata>`_.
        """
        gh_url = "https://github.com/kdeldycke/meta-package-manager"
        doc_url = "https://kdeldycke.github.io/meta-package-manager"
        self.document = Bom()
        # ``(manager_id, package_id) -> Component`` lookup, used by
        # :py:meth:`finalize` to wire declared-dependency edges to their
        # already-emitted Component instances.
        self.component_index = {}
        # ``(source_component, manager_id, target_id)`` queue: dependency
        # edges deferred because the target may not have been added yet.
        self.pending_dependencies = []

        # mpm produces an inventory of what is installed on a live system.
        self.document.metadata.lifecycles = [
            PredefinedLifecycle(phase=LifecyclePhase.OPERATIONS),
        ]

        self.document.metadata.component = Component(
            name="meta-package-manager",
            type=ComponentType.APPLICATION,
            bom_ref=f"meta-package-manager@{__version__}",
            supplier=OrganizationalEntity(
                name="Meta Package Manager",
                urls=[XsUri(gh_url)],
            ),
            version=__version__,
            purl=PackageURL(
                type="pypi", name="meta-package-manager", version=__version__
            ),
            external_references=[
                ExternalReference(
                    type=ExternalReferenceType.ADVISORIES,
                    url=XsUri(f"{gh_url}/security"),
                ),
                ExternalReference(
                    type=ExternalReferenceType.BUILD_META,
                    url=XsUri(f"{gh_url}/blob/v{__version__}/uv.lock"),
                ),
                ExternalReference(
                    type=ExternalReferenceType.BUILD_SYSTEM,
                    url=XsUri(f"{gh_url}/actions"),
                ),
                ExternalReference(
                    type=ExternalReferenceType.CONFIGURATION,
                    url=XsUri(f"{doc_url}/configuration.html"),
                ),
                ExternalReference(
                    type=ExternalReferenceType.DISTRIBUTION,
                    url=XsUri("https://pypi.org/project/meta-package-manager"),
                ),
                ExternalReference(
                    type=ExternalReferenceType.DISTRIBUTION_INTAKE,
                    url=XsUri(f"{gh_url}/releases/tag/v{__version__}"),
                ),
                ExternalReference(
                    type=ExternalReferenceType.DOCUMENTATION,
                    url=XsUri(doc_url),
                ),
                ExternalReference(
                    type=ExternalReferenceType.ISSUE_TRACKER,
                    url=XsUri(f"{gh_url}/issues"),
                ),
                ExternalReference(
                    type=ExternalReferenceType.LICENSE,
                    url=XsUri(f"{gh_url}/blob/main/license"),
                ),
                ExternalReference(
                    type=ExternalReferenceType.MATURITY_REPORT,
                    url=XsUri(f"{gh_url}/pulse"),
                ),
                ExternalReference(
                    type=ExternalReferenceType.RELEASE_NOTES,
                    url=XsUri(f"{doc_url}/changelog.html"),
                ),
                ExternalReference(
                    type=ExternalReferenceType.SOURCE_DISTRIBUTION,
                    url=XsUri(
                        f"{gh_url}/releases/download/v{__version__}"
                        f"/meta_package_manager-{__version__}.tar.gz"
                    ),
                ),
                ExternalReference(
                    type=ExternalReferenceType.VCS,
                    url=XsUri(gh_url),
                ),
                ExternalReference(
                    type=ExternalReferenceType.WEBSITE,
                    url=XsUri(gh_url),
                ),
                ExternalReference(
                    type=ExternalReferenceType.OTHER,
                    url=XsUri("https://github.com/sponsors/kdeldycke"),
                    comment="Funding",
                ),
            ],
        )

    @staticmethod
    def _supplier_for(
        manager: PackageManager, metadata: PackageMetadata
    ) -> OrganizationalEntity:
        """Map metadata's supplier (or the manager itself) to a CycloneDX
        ``OrganizationalEntity``.
        """
        if metadata.supplier:
            urls = [XsUri(metadata.supplier.url)] if metadata.supplier.url else None
            return OrganizationalEntity(name=metadata.supplier.name, urls=urls)
        return OrganizationalEntity(name=manager.name)

    @staticmethod
    def _hashes_for(metadata: PackageMetadata) -> list:
        """Build CycloneDX ``HashType`` objects from the portable
        ``Checksum`` list, dropping algorithms unsupported by 1.7.
        """
        out = []
        for c in metadata.checksums:
            algo = _CYCLONEDX_HASH_MAP.get(c.algorithm.value)
            if algo is not None:
                out.append(HashType(alg=algo, content=c.value))
        return out

    @staticmethod
    def _licenses_for(metadata: PackageMetadata) -> list:
        """Translate license metadata into CycloneDX license objects.

        Tries the parsed SPDX expression first (handles compound
        expressions like ``MIT AND Apache-2.0``). Falls back to a named
        ``DisjunctiveLicense`` for free-text strings the SPDX parser
        rejects.
        """
        # ``list[Any]`` because the function appends two different concrete
        # license-object types (``DisjunctiveLicense`` and ``LicenseExpression``)
        # whose common ancestor is not exposed in CycloneDX's public API.
        out: list[Any] = []
        candidate = metadata.license_concluded or metadata.license_declared
        if not candidate:
            return out
        parsed = _parse_license_expression(candidate)
        if parsed is not None and " " not in candidate:
            try:
                out.append(DisjunctiveLicense(id=candidate))
            except Exception:  # noqa: BLE001, S110
                # DisjunctiveLicense validation rejects some technically-valid
                # SPDX IDs (case variants, deprecated identifiers). Falling
                # through to the LicenseExpression path below is the right
                # recovery; no logging needed.
                pass
            else:
                return out
        if parsed is not None:
            # Attach SPDX canonical URLs to each identifier inside the
            # expression. ``_parse_license_expression`` has already
            # rejected every ``LicenseRef-`` and unknown-symbol case, so
            # every leaf yielded here is a known SPDX identifier (license
            # or exception). Sorting by key keeps the emitted ``details``
            # order deterministic across runs, independent of CycloneDX's
            # internal ``SortedSet``.
            identifiers = sorted(set(CycloneDX._iter_spdx_identifiers(parsed)))
            details = tuple(
                LicenseExpressionDetails(
                    license_identifier=ident,
                    url=XsUri(f"https://spdx.org/licenses/{ident}.html"),
                )
                for ident in identifiers
            )
            out.append(LicenseExpression(value=candidate, details=details))
        else:
            out.append(DisjunctiveLicense(name=candidate))
        return out

    @staticmethod
    def _iter_spdx_identifiers(node) -> Iterator[str]:
        """Walk a ``license_expression`` AST and yield each leaf SPDX
        identifier as a string.

        ``parsed.symbols`` on the top-level expression collapses a
        ``LicenseWithExceptionSymbol`` into a single symbol whose key is
        the full ``"<license> WITH <exception>"`` string, which is not
        the SPDX identifier of either component. Walk the AST instead:
        ``LicenseWithExceptionSymbol`` exposes the license and exception
        symbols separately; boolean nodes (``AND``/``OR``) expose
        children via ``args``; bare ``LicenseSymbol`` instances expose
        their identifier via ``key``. Duck-typed so this module does not
        need an explicit import of ``license_expression``'s class
        hierarchy.
        """
        if hasattr(node, "license_symbol") and hasattr(node, "exception_symbol"):
            yield node.license_symbol.key
            yield node.exception_symbol.key
        elif hasattr(node, "key"):
            yield node.key
        else:
            for arg in getattr(node, "args", ()):
                yield from CycloneDX._iter_spdx_identifiers(arg)

    @staticmethod
    def _external_references_for(metadata: PackageMetadata) -> list:
        """Map metadata URLs to CycloneDX ``externalReferences``."""
        refs = []
        if metadata.homepage:
            refs.append(
                ExternalReference(
                    type=ExternalReferenceType.WEBSITE,
                    url=XsUri(metadata.homepage),
                )
            )
        if metadata.vcs_url:
            refs.append(
                ExternalReference(
                    type=ExternalReferenceType.VCS,
                    url=XsUri(metadata.vcs_url),
                )
            )
        if metadata.issue_tracker_url:
            refs.append(
                ExternalReference(
                    type=ExternalReferenceType.ISSUE_TRACKER,
                    url=XsUri(metadata.issue_tracker_url),
                )
            )
        if metadata.distribution_url:
            refs.append(
                ExternalReference(
                    type=ExternalReferenceType.DISTRIBUTION,
                    url=XsUri(metadata.distribution_url),
                )
            )
        if metadata.download_url and metadata.download_url != metadata.distribution_url:
            refs.append(
                ExternalReference(
                    type=ExternalReferenceType.DISTRIBUTION,
                    url=XsUri(metadata.download_url),
                )
            )
        if metadata.external_sbom_path is not None:
            refs.append(
                ExternalReference(
                    type=ExternalReferenceType.BOM,
                    url=XsUri(f"file://{metadata.external_sbom_path}"),
                    comment="Per-package upstream SBOM (e.g. HOMEBREW_SBOM).",
                )
            )
        return refs

    @staticmethod
    def _properties_for(metadata: PackageMetadata) -> list:
        """Encode manager-native ``extras`` as CycloneDX ``properties``.

        Properties are namespaced under ``mpm:`` so consumers can filter
        them away when they only care about the standard fields.
        """
        out = []
        for key, value in sorted(metadata.extras.items()):
            if value is None:
                continue
            out.append(Property(name=f"mpm:{key}", value=str(value)))
        return out

    def add_package(
        self,
        manager: PackageManager,
        package: Package,
        metadata: PackageMetadata = EMPTY_METADATA,
    ) -> None:
        """
        `CycloneDX package metadata specifications
        <https://cyclonedx.org/docs/1.7/json/#components>`_.
        """
        authors = None
        if metadata.originator and not metadata.originator.is_organization:
            authors = [
                OrganizationalContact(
                    name=metadata.originator.name,
                    email=metadata.originator.email,
                )
            ]
        data = Component(
            name=package.id,
            type=ComponentType.APPLICATION,
            # pURL string, by its virtue of containing all important metadata of a
            # package, makes perfect unique IDs.
            bom_ref=package.purl.to_string(),
            group=package.manager_id,
            version=str(package.installed_version),
            description=metadata.description or package.description,
            purl=package.purl,
            supplier=self._supplier_for(manager, metadata),
            hashes=self._hashes_for(metadata),
            licenses=self._licenses_for(metadata),
            external_references=self._external_references_for(metadata),
            properties=self._properties_for(metadata),
            copyright=metadata.copyright_text,
            cpe=metadata.cpe,
            authors=authors,
        )
        self.document.components.add(data)
        self.component_index[(manager.id, package.id)] = data
        self._track_addition(manager.id, package.id, metadata)
        self.document.register_dependency(
            self.document.metadata.component,  # type:ignore[arg-type]
            [data],
        )
        for dep in metadata.dependencies:
            self.pending_dependencies.append((data, manager.id, dep.target_id))

    def all_purls(self) -> Any:
        """Yield every component purl in insertion order.

        Each component's ``bom_ref`` is its purl string, so the same
        values double as the vulnerability ``affects`` targets in
        :py:meth:`finalize`.
        """
        for component in self.component_index.values():
            if component.purl is not None:
                yield component.purl.to_string()

    def finalize(self) -> None:
        """Resolve queued dependency edges and attach vulnerability records.

        Mirrors :py:meth:`meta_package_manager.sbom.spdx.SPDX.finalize`.
        Dangling references (the dependency target is not in the inventory)
        are dropped silently.

        Vulnerability data bound via
        :py:meth:`meta_package_manager.sbom.base.SBOM.attach_vulnerabilities`
        is projected into the CycloneDX ``vulnerabilities`` array. Each
        advisory is described once at the document level with an
        ``affects`` list pointing at every component (by ``bom_ref``,
        which equals the purl) it impacts.
        """
        for source, manager_id, target_id in self.pending_dependencies:
            target = self.component_index.get((manager_id, target_id))
            if target is None:
                continue
            self.document.register_dependency(source, [target])

        self._attach_vulnerability_records()

    def _attach_vulnerability_records(self) -> None:
        """Build CycloneDX ``Vulnerability`` objects from attached data.

        Deduplicates by advisory id: an advisory that hits several
        components is emitted once with multiple ``affects`` targets.
        """
        if not self.vulnerabilities_by_purl:
            return
        purls_with_component = {
            c.purl.to_string() for c in self.component_index.values() if c.purl
        }
        by_id: dict[str, Any] = {}
        for purl_str, vulns in self.vulnerabilities_by_purl.items():
            if purl_str not in purls_with_component:
                continue
            for vuln in vulns:
                cdx_vuln = by_id.get(vuln.id)
                if cdx_vuln is None:
                    cdx_vuln = self._build_cyclonedx_vuln(vuln)
                    by_id[vuln.id] = cdx_vuln
                    self.document.vulnerabilities.add(cdx_vuln)
                cdx_vuln.affects.add(BomTarget(ref=purl_str))

    @staticmethod
    def _build_cyclonedx_vuln(vuln) -> Any:
        """Translate a portable ``Vulnerability`` into a CycloneDX one.

        ``vuln`` is a
        :py:class:`meta_package_manager.sbom.vulnerabilities.Vulnerability`;
        left untyped so this module need not import the network-side
        module when the ``[sbom-online]`` extra is absent.
        """
        source = VulnerabilitySource(
            name=vuln.source,
            url=XsUri(vuln.advisory_url) if vuln.advisory_url else None,
        )
        ratings = []
        severity = _CYCLONEDX_SEVERITY_MAP.get(vuln.severity or "")
        if severity is not None or vuln.cvss_vector:
            ratings.append(
                VulnerabilityRating(
                    source=source,
                    severity=severity,
                    vector=vuln.cvss_vector,
                )
            )
        # OSV CWE ids look like "CWE-79"; CycloneDX wants the bare integer.
        cwes = []
        for cwe in vuln.cwe_ids:
            digits = cwe.removeprefix("CWE-")
            if digits.isdigit():
                cwes.append(int(digits))
        references = [
            VulnerabilityReference(id=alias, source=source)
            for alias in vuln.aliases
        ]
        advisories = [
            VulnerabilityAdvisory(url=XsUri(url)) for url in vuln.references
        ]
        return CDXVulnerability(
            id=vuln.id,
            source=source,
            description=vuln.summary,
            detail=vuln.description,
            ratings=ratings,
            cwes=cwes,
            references=references,
            advisories=advisories,
            published=vuln.published_date,
            updated=vuln.modified_date,
        )

    def stats(self) -> dict[str, object]:
        """Extend the base stats with CycloneDX-specific counters.

        CycloneDX has no merge-content equivalent: per-package upstream
        SBOMs are linked through ``externalReferences[type=bom]`` rather
        than spliced in. The merged-document count therefore reports the
        number of components carrying a BOM external reference. The
        dependency-edge total walks the registered dependency graph and
        sums the ``dependsOn`` collection size across every entry.
        """
        base = super().stats()
        components_with_bom = sum(
            1
            for component in self.document.components
            for ref in component.external_references
            if ref.type == ExternalReferenceType.BOM
        )
        dependency_edges = sum(
            len(dep.dependencies) for dep in self.document.dependencies
        )
        base.update({
            "components_in_document": len(self.document.components),
            "external_bom_references": components_with_bom,
            "dependency_edges": dependency_edges,
        })
        return base

    def export(self) -> str:
        """Serialize the document to its string representation.

        .. note::

            Unlike :py:meth:`meta_package_manager.sbom.spdx.SPDX.export`, the generated document is not
            validated against its schema here. CycloneDX schema validation
            relies on ``cyclonedx-python-lib``'s ``[validation]`` extra, which
            pulls in ``jsonschema`` and, transitively, ``rfc3987-syntax``,
            ``lark``, and ``lxml``. To keep that stack out of ``mpm``'s runtime
            dependencies, the validation runs in the test suite instead. See
            ``tests/test_cli_sbom.py``.
        """
        if self.export_format == ExportFormat.JSON:
            return str(JsonV1Dot7(self.document).output_as_string(indent=2))

        if self.export_format == ExportFormat.XML:
            writer = make_outputter(self.document, OutputFormat.XML, SchemaVersion.V1_7)
            return str(writer.output_as_string(indent=2))

        raise ValueError(f"{self.export_format} not supported.")
