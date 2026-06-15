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

Defines the :py:class:`meta_package_manager.sbom.SBOM` base and its
:py:class:`meta_package_manager.sbom.SPDX` and
:py:class:`meta_package_manager.sbom.CycloneDX` implementations, which serialize the
:py:class:`meta_package_manager.package.Package` objects collected from the managers
into the two dominant standardized SBOM formats.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import sys
from datetime import datetime, timezone

from boltons.ecoutils import get_profile
from extra_platforms import current_platform
from packageurl import PackageURL

from . import __version__
from .sbom_metadata import (
    EMPTY_METADATA,
    Checksum,
    ChecksumAlgorithm,
    Dependency,
    DependencyScope,
    PackageMetadata,
)

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
    from cyclonedx.model.dependency import Dependency as CycloneDXDependency
    from cyclonedx.model.license import DisjunctiveLicense, LicenseExpression
    from cyclonedx.model.lifecycle import LifecyclePhase, PredefinedLifecycle
    from cyclonedx.output import make_outputter
    from cyclonedx.output.json import JsonV1Dot7
    from cyclonedx.schema import OutputFormat, SchemaVersion
except ImportError:
    cyclonedx_support = False
    logging.getLogger("meta_package_manager").debug(
        "CycloneDX support disabled: "
        "install meta-package-manager[sbom] to enable it.",
    )

spdx_support = True
try:
    from spdx_tools.common.spdx_licensing import spdx_licensing
    from spdx_tools.spdx.model import (
        Actor,
        ActorType,
        CreationInfo,
        Document,
        ExternalDocumentRef,
        ExternalPackageRef,
        ExternalPackageRefCategory,
        PackagePurpose,
        Relationship,
        RelationshipType,
        SpdxNoAssertion,
        SpdxNone,
    )
    from spdx_tools.spdx.model import (
        Checksum as SPDXChecksum,
    )
    from spdx_tools.spdx.model import (
        ChecksumAlgorithm as SPDXChecksumAlgorithm,
    )
    from spdx_tools.spdx.model import (
        Package as SPDXPackage,
    )
    from spdx_tools.spdx.validation.document_validator import (
        validate_full_spdx_document,
    )
    from spdx_tools.spdx.writer.json import json_writer
    from spdx_tools.spdx.writer.rdf import rdf_writer
    from spdx_tools.spdx.writer.tagvalue import tagvalue_writer
    from spdx_tools.spdx.writer.write_utils import convert
    from spdx_tools.spdx.writer.xml import xml_writer
    from spdx_tools.spdx.writer.yaml import yaml_writer
except ImportError:
    spdx_support = False
    logging.getLogger("meta_package_manager").debug(
        "SPDX support disabled: install meta-package-manager[sbom] to enable it.",
    )

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from backports.strenum import StrEnum  # type: ignore[import-not-found]

TYPE_CHECKING = False
if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any

    from .manager import PackageManager
    from .package import Package


class ExportFormat(StrEnum):
    """A user-friendly version of ``spdx_tools.spdx.formats.FileFormat``.

    Map format to user-friendly IDs.
    """

    JSON = "json"
    XML = "xml"
    YAML = "yaml"
    TAG_VALUE = "tag"
    RDF_XML = "rdf"


class SBOM:
    """Utilities shared by all SBOM classes."""

    bundled_scan: bool = True
    """Whether the scan was a ``--bundled`` enrichment pass.

    Set by :py:meth:`set_scan_completeness` from the CLI. ``True`` means
    the metadata extractors ran and upstream per-package SBOMs were
    merged (the default). ``False`` is the ``--minimal`` mode: bare
    inventory only, no extractor calls. Subclasses use this flag to
    populate completeness markers in their respective standards
    (``incomplete`` vs ``complete`` in CycloneDX, ``EXTRACTED`` license
    handling in SPDX).
    """

    def __init__(
        self,
        export_format: ExportFormat = ExportFormat.JSON,  # type: ignore[assignment]
    ) -> None:
        """Defaults to JSON export format."""
        logging.debug(f"Set export format to {export_format}")
        self.export_format = export_format

    def set_scan_completeness(self, bundled: bool) -> None:
        """Record whether the run was a bundled enrichment pass.

        Called once by the CLI right after :py:meth:`init_doc` and before
        the first :py:meth:`add_package`. The information flows into
        per-format completeness markers in the rendered document.
        """
        self.bundled_scan = bundled

    def finalize(self) -> None:
        """Resolve any deferred state before :py:meth:`export`.

        Some constructs cannot be emitted at :py:meth:`add_package` time
        because they reference packages that may not have been added yet:
        a Homebrew formula's runtime dependency on another formula listed
        later in the scan, for example. Subclasses queue those during
        ``add_package`` and flush them here. The base implementation is a
        no-op so subclasses can rely on it being called exactly once.
        """

    @staticmethod
    def autodetect_export_format(file_path: Path) -> ExportFormat | None:
        """Better version of ``spdx_tools.spdx.formats.file_name_to_format`` which is
        based on ``Path`` objects and is case-insensitive.

        .. todo:
            Contribute generic autodetection method to Click Extra?
        """
        suffixes = tuple(s.lower() for s in file_path.suffixes[-2:])
        export_format = None
        if suffixes:
            if suffixes == (".rdf", ".xml") or suffixes[-1] == ".rdf":
                export_format = ExportFormat.RDF_XML
            elif suffixes[-1] == ".json":
                export_format = ExportFormat.JSON
            elif suffixes[-1] == ".xml":
                export_format = ExportFormat.XML
            elif suffixes[-1] in (".yaml", ".yml"):
                export_format = ExportFormat.YAML
            elif suffixes[-1] in (".tag", ".spdx"):
                export_format = ExportFormat.TAG_VALUE
        logging.debug(f"File suffixes {suffixes} resolves to {export_format}.")
        return export_format  # type: ignore[return-value]


_SPDX_CHECKSUM_MAP: dict[str, object] = {}
_CYCLONEDX_HASH_MAP: dict[str, object] = {}
_SPDX_RELATIONSHIP_MAP: dict[str, object] = {}
if spdx_support:
    _SPDX_CHECKSUM_MAP = {
        ChecksumAlgorithm.MD5.value: SPDXChecksumAlgorithm.MD5,
        ChecksumAlgorithm.SHA1.value: SPDXChecksumAlgorithm.SHA1,
        ChecksumAlgorithm.SHA256.value: SPDXChecksumAlgorithm.SHA256,
        ChecksumAlgorithm.SHA512.value: SPDXChecksumAlgorithm.SHA512,
        ChecksumAlgorithm.SHA3_256.value: SPDXChecksumAlgorithm.SHA3_256,
        ChecksumAlgorithm.SHA3_512.value: SPDXChecksumAlgorithm.SHA3_512,
        ChecksumAlgorithm.BLAKE2B_256.value: SPDXChecksumAlgorithm.BLAKE2B_256,
        ChecksumAlgorithm.BLAKE2B_512.value: SPDXChecksumAlgorithm.BLAKE2B_512,
    }
    _SPDX_RELATIONSHIP_MAP = {
        DependencyScope.RUNTIME.value: RelationshipType.RUNTIME_DEPENDENCY_OF,
        DependencyScope.BUILD.value: RelationshipType.BUILD_DEPENDENCY_OF,
        DependencyScope.DEV.value: RelationshipType.DEV_DEPENDENCY_OF,
        DependencyScope.OPTIONAL.value: RelationshipType.OPTIONAL_DEPENDENCY_OF,
        DependencyScope.TEST.value: RelationshipType.TEST_DEPENDENCY_OF,
        DependencyScope.RECOMMENDED.value: RelationshipType.OPTIONAL_DEPENDENCY_OF,
    }
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


def _parse_license_expression(expression: str):
    """Best-effort parse of a free-text license string.

    Returns a ``LicenseExpression`` from the ``license_expression``
    library when the string parses *and* uses only symbols known to
    ``spdx_licensing`` (the SPDX license list plus declared
    exceptions). Returns ``None`` when the string is missing, fails
    parsing, or references unknown ``LicenseRef-`` identifiers. Why
    reject parseable-but-unknown symbols: SPDX validation requires every
    ``LicenseRef-Xxx`` symbol to be declared in the document's
    ``hasExtractedLicensingInfos`` block. Brew's per-formula files emit
    ``LicenseRef-Homebrew-public-domain`` and similar without that
    declaration; passing them through would trip the validator. Falling
    back to ``SpdxNoAssertion`` at the call site keeps the export valid
    at the cost of one bit of information per package.
    """
    if not spdx_support or not expression:
        return None
    try:
        parsed = spdx_licensing.parse(expression)
    except Exception:
        return None
    if parsed is None:
        return None
    for symbol in parsed.symbols:
        key = getattr(symbol, "key", None) or str(symbol)
        if key.startswith("LicenseRef-"):
            return None
        if not spdx_licensing.validate(key).errors == []:
            return None
    return parsed


def _coerce_spdx_string(raw):
    """Map upstream SPDX sentinel strings to their typed counterparts.

    SPDX JSON files serialize ``NOASSERTION`` and ``NONE`` as plain
    strings; the ``spdx_tools`` validator rejects those at the Python
    layer and demands the typed singletons. The merge path runs every
    string field that allows the union through this helper before
    handing it to the typed ``Package`` constructor.
    """
    if not isinstance(raw, str):
        return raw
    upper = raw.strip().upper()
    if upper == "NOASSERTION":
        return SpdxNoAssertion()
    if upper == "NONE":
        return SpdxNone()
    return raw


class SPDX(SBOM):
    """Generates an SPDX document from a list of packages.

    `SPDX 2.3 specifications <https://spdx.github.io/spdx-spec/v2.3/>`_.
    """

    DOC_ID = "SPDXRef-DOCUMENT"
    """Document root ID."""

    document: Document
    seen_ids: set[str]
    name_index: dict[tuple[str, str], str]
    pending_relationships: list[tuple[str, str, str, object]]
    merged_docs: dict[str, str]

    @classmethod
    def normalize_spdx_id(cls, str: str) -> str:
        """SPDX IDs must only contain letters, numbers, ``.`` and ``-``."""
        return "-".join(s for s in re.split(r"[^a-zA-Z0-9\.]", str) if s)

    def init_doc(self) -> None:
        """
        `SPDX document metadata specifications
        <https://spdx.github.io/spdx-spec/v2.3/document-creation-information/>`_.
        """
        profile = get_profile()
        system_id = self.normalize_spdx_id(
            "-".join(
                (
                    current_platform().name,
                    profile["linux_dist_name"],
                    profile["linux_dist_version"],
                    profile["uname"]["system"],
                    profile["uname"]["release"],
                    profile["uname"]["machine"],
                )
            )
        )

        self.seen_ids = set()
        # ``(manager_id, package_id) -> SPDX docid`` lookup used by
        # :py:meth:`finalize` to resolve declared dependencies into
        # ``Relationship`` entries. Populated by every :py:meth:`add_package`
        # call so cross-package edges can be wired up at the end of the scan
        # regardless of the order managers report their packages in.
        self.name_index = {}
        # Each entry is ``(source_docid, manager_id, target_id, relationship_type)``.
        # The renderer cannot turn declared dependencies into relationships
        # immediately because the dependency target may not have been added
        # yet. Resolved in :py:meth:`finalize`.
        self.pending_relationships = []
        # ``document_ref_id -> SHA1`` for every per-package upstream SPDX file
        # we merged. Drives the ``externalDocumentRefs`` document section so
        # consumers can trace which slice of our aggregate doc came from
        # which Homebrew formula's ``sbom.spdx.json``.
        self.merged_docs = {}
        self.document = Document(
            CreationInfo(
                spdx_version="SPDX-2.3",
                spdx_id=self.DOC_ID,
                # Because mpm is a system-wide tool, we chose to name the document
                # after the host operating system platform it was run on.
                name=system_id,
                # Point directly to the mpm release on GitHub so we can get some
                # additional meaning from an URI that is not supposed to have any
                # meaning. We add a trailing "/<random_unique_id>" to the URI as the
                # namespace is supposed to be unique for each document. See:
                # https://spdx.github.io/spdx-spec/v2.3/document-creation-information/#65-spdx-document-namespace-field
                document_namespace=(
                    "https://github.com/kdeldycke/meta-package-manager/releases/tag/"
                    f"v{__version__}/{profile['guid']}"
                ),
                creators=[Actor(ActorType.TOOL, f"meta-package-manager-{__version__}")],
                created=datetime.now(tz=timezone.utc),
                data_license="CC0-1.0",
            )
        )

    def _supplier_for(
        self, manager: PackageManager, metadata: PackageMetadata
    ) -> object:
        """Build the SPDX supplier ``Actor``.

        The manager name is the fallback (Homebrew, PyPI, ...). If the
        metadata extractor surfaces a more specific supplier (a tap, a
        downstream redistributor) it wins.
        """
        if metadata.supplier:
            return Actor(ActorType.ORGANIZATION, metadata.supplier.name)
        return Actor(ActorType.ORGANIZATION, manager.name)

    @staticmethod
    def _originator_for(metadata: PackageMetadata):
        """Build the SPDX originator ``Actor`` from upstream metadata."""
        if metadata.originator is None:
            return None
        actor_type = (
            ActorType.ORGANIZATION
            if metadata.originator.is_organization
            else ActorType.PERSON
        )
        return Actor(actor_type, metadata.originator.name, metadata.originator.email)

    @staticmethod
    def _checksums_for(metadata: PackageMetadata) -> list:
        """Translate ``PackageMetadata`` checksums into SPDX ``Checksum`` objects.

        Algorithms unsupported by SPDX 2.3 are silently dropped: the
        renderer never emits an invalid checksum entry.
        """
        out = []
        for c in metadata.checksums:
            algo = _SPDX_CHECKSUM_MAP.get(c.algorithm.value)
            if algo is not None:
                out.append(SPDXChecksum(algo, c.value))
        return out

    @staticmethod
    def _license_or_noassertion(expression: str | None):
        """Coerce a free-text license string into the SPDX license union.

        Returns a ``LicenseExpression`` on success, ``SpdxNoAssertion()``
        when the string is missing, an upstream ``NOASSERTION`` sentinel,
        or fails strict parsing. The validator rejects a literal
        ``LicenseSymbol('NOASSERTION')``, so we hand back the typed
        ``SpdxNoAssertion()`` directly: same intent, validation-clean.
        """
        if not expression:
            return None
        upper = expression.strip().upper()
        if upper == "NOASSERTION":
            return SpdxNoAssertion()
        if upper == "NONE":
            return SpdxNone()
        parsed = _parse_license_expression(expression)
        if parsed is None:
            return SpdxNoAssertion()
        return parsed

    def _external_refs_for(
        self,
        package: Package,
        metadata: PackageMetadata,
    ) -> list:
        """Assemble the SPDX ``externalRefs`` block.

        Always includes the package's primary purl. CPE strings (when
        provided) land as a security-category ``cpe23Type`` ref. Extra
        purls (multi-arch or multi-origin variants) become additional
        package-manager refs.
        """
        refs = [
            ExternalPackageRef(
                ExternalPackageRefCategory.PACKAGE_MANAGER,
                "purl",
                package.purl.to_string(),
            )
        ]
        for extra in metadata.extra_purls:
            refs.append(
                ExternalPackageRef(
                    ExternalPackageRefCategory.PACKAGE_MANAGER,
                    "purl",
                    extra.to_string(),
                )
            )
        if metadata.cpe:
            refs.append(
                ExternalPackageRef(
                    ExternalPackageRefCategory.SECURITY,
                    "cpe23Type",
                    metadata.cpe,
                )
            )
        return refs

    def add_package(
        self,
        manager: PackageManager,
        package: Package,
        metadata: PackageMetadata = EMPTY_METADATA,
    ) -> None:
        """
        `SPDX package metadata specifications
        <https://spdx.github.io/spdx-spec/v2.3/package-information/>`_.
        """
        # pURL string, by its virtue of containing all important metadata of a package,
        # makes perfect unique IDs.
        package_docid = self.normalize_spdx_id(f"SPDXRef-{package.purl}")
        # Some managers (e.g. CPAN) list the same package multiple times.
        if package_docid in self.seen_ids:
            logging.debug(f"Skip duplicate package {package_docid}.")
            return
        self.seen_ids.add(package_docid)
        self.name_index[(manager.id, package.id)] = package_docid

        download_location = metadata.download_url or SpdxNoAssertion()
        homepage = metadata.homepage or None
        # SPDX requires ``files_analyzed=True`` only when the renderer also
        # emits per-file entries. We keep it ``False`` for inventory-level
        # snapshots: any extractor that captures file lists today (pip
        # ``RECORD``, dpkg ``.md5sums``) stores them in
        # ``PackageMetadata.files``, but the SPDX File model is not wired
        # in yet. Promoting to ``True`` is safe to do later when that
        # writer lands.
        files_analyzed = metadata.files_analyzed

        license_concluded = self._license_or_noassertion(metadata.license_concluded)
        license_declared = self._license_or_noassertion(metadata.license_declared)
        copyright_text = metadata.copyright_text or None

        self.document.packages.append(
            SPDXPackage(
                name=package.id,
                spdx_id=package_docid,
                version=str(package.installed_version),
                supplier=self._supplier_for(manager, metadata),
                originator=self._originator_for(metadata),
                download_location=download_location,
                files_analyzed=files_analyzed,
                checksums=self._checksums_for(metadata),
                homepage=homepage,
                license_concluded=license_concluded,
                license_declared=license_declared,
                copyright_text=copyright_text,
                summary=metadata.summary or package.name,
                description=metadata.description or package.description,
                external_references=self._external_refs_for(package, metadata),
                primary_package_purpose=PackagePurpose.INSTALL,
                release_date=metadata.release_date,
                built_date=metadata.build_date,
            )
        )

        # A DESCRIBES relationship asserts that the document indeed describes the
        # package.
        self.document.relationships.append(
            Relationship(self.DOC_ID, RelationshipType.DESCRIBES, package_docid)
        )

        # Queue declared dependencies for finalize() resolution. We cannot
        # emit the Relationship now because the target may not have been
        # added yet (apt dependencies often point at packages later in the
        # scan, brew deps may sit in a tap not yet processed).
        for dep in metadata.dependencies:
            rel_type = _SPDX_RELATIONSHIP_MAP.get(
                dep.scope.value, RelationshipType.DEPENDS_ON
            )
            self.pending_relationships.append(
                (package_docid, manager.id, dep.target_id, rel_type)
            )

        # Pull rich data from an upstream per-package SBOM if present.
        if metadata.external_sbom_path is not None:
            try:
                self._merge_external_sbom(
                    package_docid=package_docid,
                    package=package,
                    manager_id=manager.id,
                    sbom_path=metadata.external_sbom_path,
                )
            except Exception as exc:
                logging.debug(
                    f"Failed to merge external SBOM {metadata.external_sbom_path}: "
                    f"{exc}",
                )

    def _merge_external_sbom(
        self,
        package_docid: str,
        package: Package,
        manager_id: str,
        sbom_path,
    ) -> None:
        """Splice a per-package upstream SPDX file into the aggregate document.

        Brew formulae installed with ``HOMEBREW_SBOM=1`` write
        ``<prefix>/sbom.spdx.json`` per formula. The document carries the
        full upstream dependency closure with real download URLs, real
        checksums, real licenses. We adopt its child packages (transitive
        deps), prefix their SPDX IDs with the manager/formula namespace
        to avoid collisions, and re-wire relationship targets accordingly.

        The root package in the upstream file matches the formula we just
        added; we drop it from the merge (its slot in the aggregate doc
        is already taken by the entry the inventory pass produced) and
        rewire any relationships that pointed at it so they point at our
        already-emitted ``package_docid``.

        Errors are caught one level up: a single malformed upstream file
        must not abort the entire scan.
        """
        with open(sbom_path, "rb") as fh:
            data = fh.read()
        digest = hashlib.sha1(data).hexdigest()
        upstream = json.loads(data)

        doc_ref_id = self.normalize_spdx_id(
            f"DocumentRef-{manager_id}-{package.id}"
        )
        # SPDX IDs are matched textually. Keep the prefix terse but
        # collision-free across formulae sharing common dep names.
        local_prefix = self.normalize_spdx_id(
            f"SPDXRef-{manager_id}-{package.id}"
        )
        upstream_packages = upstream.get("packages") or []
        upstream_relationships = upstream.get("relationships") or []

        upstream_root = upstream.get("documentDescribes") or []
        upstream_root_id = upstream_root[0] if upstream_root else None
        # Map upstream IDs to their relocated counterparts in our document.
        id_map: dict[str, str] = {}
        if upstream_root_id:
            id_map[upstream_root_id] = package_docid

        # Pass 1: register every transitive package under our prefix and
        # add it to the document. Skip the root (already represented in
        # the aggregate by our inventory entry).
        for upstream_pkg in upstream_packages:
            upstream_id = upstream_pkg.get("SPDXID")
            if not upstream_id or upstream_id == upstream_root_id:
                continue
            new_id = self.normalize_spdx_id(
                f"{local_prefix}-{upstream_pkg.get('name', upstream_id)}"
            )
            # Ensure uniqueness even across merged formulae touching the
            # same transitive dep.
            disambiguator = 1
            base_new_id = new_id
            while new_id in self.seen_ids:
                disambiguator += 1
                new_id = f"{base_new_id}-{disambiguator}"
            self.seen_ids.add(new_id)
            id_map[upstream_id] = new_id

            self.document.packages.append(
                SPDXPackage(
                    name=upstream_pkg.get("name", upstream_id),
                    spdx_id=new_id,
                    version=upstream_pkg.get("versionInfo"),
                    supplier=Actor(ActorType.ORGANIZATION, "Upstream (merged)"),
                    download_location=_coerce_spdx_string(
                        upstream_pkg.get("downloadLocation"),
                    )
                    or SpdxNoAssertion(),
                    files_analyzed=False,
                    homepage=_coerce_spdx_string(upstream_pkg.get("homepage")) or None,
                    license_declared=self._license_or_noassertion(
                        upstream_pkg.get("licenseDeclared"),
                    ),
                    license_concluded=self._license_or_noassertion(
                        upstream_pkg.get("licenseConcluded"),
                    ),
                    copyright_text=_coerce_spdx_string(
                        upstream_pkg.get("copyrightText"),
                    )
                    or None,
                    summary=upstream_pkg.get("summary"),
                    description=upstream_pkg.get("description"),
                    primary_package_purpose=PackagePurpose.LIBRARY,
                )
            )

        # Pass 2: rewrite relationships. We only port the dependency-type
        # edges; the upstream DESCRIBES relationships are already covered
        # by our own DESCRIBES emission above.
        for rel in upstream_relationships:
            rel_type_str = rel.get("relationshipType")
            if not rel_type_str or rel_type_str == "DESCRIBES":
                continue
            try:
                rel_type = RelationshipType[rel_type_str]
            except KeyError:
                continue
            src = id_map.get(rel.get("spdxElementId"))
            tgt = id_map.get(rel.get("relatedSpdxElement"))
            if not src or not tgt:
                continue
            self.document.relationships.append(Relationship(src, rel_type, tgt))

        # Record the upstream document for traceability.
        self.merged_docs[doc_ref_id] = digest
        self.document.creation_info.external_document_refs.append(
            ExternalDocumentRef(
                document_ref_id=doc_ref_id,
                document_uri=upstream.get("documentNamespace")
                or f"file://{sbom_path}",
                checksum=SPDXChecksum(SPDXChecksumAlgorithm.SHA1, digest),
            )
        )

    def finalize(self) -> None:
        """Emit pending dependency relationships.

        Walks the queue built by :py:meth:`add_package` and emits each
        relationship only when both ends resolve to packages we actually
        included in the document. Dangling references (the target package
        is not installed) are dropped silently: the SBOM only describes
        what is on the system, not what could be.
        """
        for source_docid, manager_id, target_id, rel_type in self.pending_relationships:
            target_docid = self.name_index.get((manager_id, target_id))
            if not target_docid:
                continue
            self.document.relationships.append(
                Relationship(target_docid, rel_type, source_docid)
            )

    def export(self) -> str:
        """Similar to ``spdx_tools.spdx.writer.write_anything.write_file`` but write
        directly to provided stream instead of file path.
        """
        stream = io.StringIO()

        writer: Any
        if self.export_format == ExportFormat.JSON:
            writer = json_writer
        elif self.export_format == ExportFormat.XML:
            writer = xml_writer
        elif self.export_format == ExportFormat.YAML:
            writer = yaml_writer
        elif self.export_format == ExportFormat.TAG_VALUE:
            writer = tagvalue_writer
        elif self.export_format == ExportFormat.RDF_XML:
            writer = rdf_writer
            # RDF writer expects a binary-mode IO stream.
            stream = io.BytesIO()  # type: ignore[assignment]
        else:
            raise ValueError(f"{self.export_format} not supported.")

        logging.debug("Validate document...")
        errors = validate_full_spdx_document(self.document)
        if errors:
            document_dict = convert(self.document, None)  # type: ignore[arg-type]
            logging.debug(document_dict)
            raise ValueError(f"Document is not valid. Errors: {errors}")

        logging.debug(f"Export with {writer.__name__}")
        writer.write_document_to_stream(self.document, stream, validate=False)
        return stream.getvalue()


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
        out = []
        candidate = metadata.license_concluded or metadata.license_declared
        if not candidate:
            return out
        parsed = _parse_license_expression(candidate)
        if parsed is not None and " " not in candidate:
            try:
                out.append(DisjunctiveLicense(id=candidate))
                return out
            except Exception:
                pass
        if parsed is not None:
            out.append(LicenseExpression(value=candidate))
        else:
            out.append(DisjunctiveLicense(name=candidate))
        return out

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
        self.document.register_dependency(
            self.document.metadata.component,  # type:ignore[arg-type]
            [data],
        )
        for dep in metadata.dependencies:
            self.pending_dependencies.append((data, manager.id, dep.target_id))

    def finalize(self) -> None:
        """Resolve queued dependency edges between Components.

        Mirrors :py:meth:`SPDX.finalize`. Dangling references (the
        dependency target is not in the inventory) are dropped silently.
        """
        for source, manager_id, target_id in self.pending_dependencies:
            target = self.component_index.get((manager_id, target_id))
            if target is None:
                continue
            self.document.register_dependency(source, [target])

    def export(self) -> str:
        """Serialize the document to its string representation.

        .. note::

            Unlike :py:meth:`SPDX.export`, the generated document is not
            validated against its schema here. CycloneDX schema validation
            relies on ``cyclonedx-python-lib``'s ``[validation]`` extra, which
            pulls in ``jsonschema`` and, transitively, ``rfc3987-syntax``,
            ``lark``, and ``lxml``. To keep that stack out of ``mpm``'s runtime
            dependencies, the validation runs in the test suite instead. See
            ``tests/test_cli_sbom.py``.
        """
        if self.export_format == ExportFormat.JSON:
            return JsonV1Dot7(self.document).output_as_string(indent=2)

        if self.export_format == ExportFormat.XML:
            writer = make_outputter(self.document, OutputFormat.XML, SchemaVersion.V1_7)
            return writer.output_as_string(indent=2)

        raise ValueError(f"{self.export_format} not supported.")
