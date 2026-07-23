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
"""SPDX 2.3 writer plus the per-package upstream-SBOM merge logic.

Heavy `spdx_tools` imports are guarded behind a `try/except` block so
this module is importable even when the optional `[sbom-offline]` extra is
not installed; in that case `spdx_support` is `False` and the
{class}`SPDX` class is still defined for type-hint compatibility but
will not function (every public method depends on the missing imports).

`_parse_license_expression` and `_coerce_spdx_string` live here
because they both touch `spdx_tools` types; {mod}`.cyclonedx`
imports the former for its own license normalization, which is one-way
and acyclic.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
from datetime import datetime, timezone
from typing import cast

from boltons.ecoutils import get_profile
from extra_platforms import current_platform

from .. import __version__
from ..package import (
    EMPTY_METADATA,
    ChecksumAlgorithm,
    DependencyScope,
    PackageMetadata,
)
from .base import SBOM, ExportFormat

spdx_support = True
try:
    from spdx_tools.common.spdx_licensing import (  # type: ignore[import-untyped]
        spdx_licensing,
    )
    from spdx_tools.spdx.model import (
        Actor,
        ActorType,
        Checksum as SPDXChecksum,
        ChecksumAlgorithm as SPDXChecksumAlgorithm,
        CreationInfo,
        Document,
        ExternalDocumentRef,
        ExternalPackageRef,
        ExternalPackageRefCategory,
        Package as SPDXPackage,
        PackagePurpose,
        Relationship,
        RelationshipType,
        SpdxNoAssertion,
        SpdxNone,
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
        "SPDX support disabled: "
        "install meta-package-manager[sbom-offline] to enable it.",
    )

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Any

    from ..manager import PackageManager
    from ..package import Package


# `Any`-valued maps to dodge cascading mypy errors at every call site: the
# values are typed instances of `spdx_tools` enums but the conditional
# `try/except` import above hides that fact from the type checker.
_SPDX_CHECKSUM_MAP: dict[str, Any] = {}
_SPDX_RELATIONSHIP_MAP: dict[str, Any] = {}
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


def _parse_license_expression(expression: str):
    """Best-effort parse of a free-text license string.

    Returns a `LicenseExpression` from the `license_expression`
    library when the string parses *and* uses only symbols known to
    `spdx_licensing` (the SPDX license list plus declared
    exceptions). Returns `None` when the string is missing, fails
    parsing, or references unknown `LicenseRef-` identifiers. Why
    reject parseable-but-unknown symbols: SPDX validation requires every
    `LicenseRef-Xxx` symbol to be declared in the document's
    `hasExtractedLicensingInfos` block. Brew's per-formula files emit
    `LicenseRef-Homebrew-public-domain` and similar without that
    declaration; passing them through would trip the validator. Falling
    back to `SpdxNoAssertion` at the call site keeps the export valid
    at the cost of one bit of information per package.
    """
    if not spdx_support or not expression:
        return None
    try:
        parsed = spdx_licensing.parse(expression)
    except Exception:  # noqa: BLE001
        return None
    if parsed is None:
        return None
    for symbol in parsed.symbols:
        key = getattr(symbol, "key", None) or str(symbol)
        if key.startswith("LicenseRef-"):
            return None
        if spdx_licensing.validate(key).errors != []:
            return None
    return parsed


def _coerce_spdx_string(raw):
    """Map upstream SPDX sentinel strings to their typed counterparts.

    SPDX JSON files serialize `NOASSERTION` and `NONE` as plain
    strings; the `spdx_tools` validator rejects those at the Python
    layer and demands the typed singletons. The merge path runs every
    string field that allows the union through this helper before
    handing it to the typed `Package` constructor.
    """
    if not isinstance(raw, str):
        return raw
    upper = raw.strip().upper()
    if upper == "NOASSERTION":
        return SpdxNoAssertion()
    if upper == "NONE":
        return SpdxNone()
    return raw


def _vuln_comment(vuln) -> str:
    """Render a one-line human summary for an SPDX security `externalRef`.

    SPDX 2.3 cannot model severity, CWE, or fixed versions structurally,
    so the most useful per-advisory facts are folded into the ref's free-
    text comment. `vuln` is a
    {class}`meta_package_manager.sbom.vulnerabilities.Vulnerability`;
    the parameter is untyped to avoid importing the network-side module
    at runtime when the `[sbom-online]` extra is absent.
    """
    parts = [vuln.id]
    if vuln.severity:
        parts.append(f"severity={vuln.severity}")
    if vuln.aliases:
        parts.append(f"aliases={', '.join(vuln.aliases)}")
    if vuln.fixed_versions:
        parts.append(f"fixed in {', '.join(vuln.fixed_versions)}")
    if vuln.summary:
        parts.append(vuln.summary)
    return " | ".join(parts)


class SPDX(SBOM):
    """Generates an SPDX document from a list of packages.

    [SPDX 2.3 specifications](https://spdx.github.io/spdx-spec/v2.3/).
    """

    DOC_ID = "SPDXRef-DOCUMENT"
    """Document root ID."""

    document: Document
    seen_ids: set[str]
    name_index: dict[tuple[str, str], str]
    # 4th tuple slot is a `RelationshipType` instance; typed as `Any`
    # because that enum is only importable when the `[sbom-offline]` extra is.
    pending_relationships: list[tuple[str, str, str, Any]]
    merged_docs: dict[str, str]

    @classmethod
    def normalize_spdx_id(cls, value: str) -> str:
        """SPDX IDs must only contain letters, numbers, `.` and `-`."""
        return "-".join(s for s in re.split(r"[^a-zA-Z0-9\.]", value) if s)

    def init_doc(self) -> None:
        """
        [SPDX document metadata specifications](https://spdx.github.io/spdx-spec/v2.3/document-creation-information/).
        """
        profile = get_profile()
        system_id = self.normalize_spdx_id(
            "-".join((
                current_platform().name,
                profile["linux_dist_name"],
                profile["linux_dist_version"],
                profile["uname"]["system"],
                profile["uname"]["release"],
                profile["uname"]["machine"],
            ))
        )

        self.seen_ids = set()
        # `(manager_id, package_id) -> SPDX docid` lookup used by
        # {meth}`finalize` to resolve declared dependencies into
        # `Relationship` entries. Populated by every {meth}`add_package`
        # call so cross-package edges can be wired up at the end of the scan
        # regardless of the order managers report their packages in.
        self.name_index = {}
        # `purl string -> docid` and `docid -> SPDXPackage` indexes used
        # to attach vulnerability data (keyed by purl) onto the right
        # package object during {meth}`finalize`.
        self.purl_index: dict[str, str] = {}
        self.package_by_docid: dict[str, Any] = {}
        # Each entry is `(source_docid, manager_id, target_id, relationship_type)`.
        # The renderer cannot turn declared dependencies into relationships
        # immediately because the dependency target may not have been added
        # yet. Resolved in {meth}`finalize`.
        self.pending_relationships = []
        # `document_ref_id -> SHA1` for every per-package upstream SPDX file
        # we merged. Drives the `externalDocumentRefs` document section so
        # consumers can trace which slice of our aggregate doc came from
        # which Homebrew formula's `sbom.spdx.json`.
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

    def _supplier_for(self, manager: PackageManager, metadata: PackageMetadata) -> Any:
        """Build the SPDX supplier `Actor`.

        The manager name is the fallback (Homebrew, PyPI, ...). If the
        metadata extractor surfaces a more specific supplier (a tap, a
        downstream redistributor) it wins.

        Returns `Any` rather than `Actor` because `Actor` is conditionally
        imported behind the `[sbom-offline]` extra: annotating with it would make this
        module fail type-checking when the extra is not installed.
        """
        if metadata.supplier:
            return Actor(ActorType.ORGANIZATION, metadata.supplier.name)
        return Actor(ActorType.ORGANIZATION, manager.name)

    @staticmethod
    def _originator_for(metadata: PackageMetadata):
        """Build the SPDX originator `Actor` from upstream metadata."""
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
        """Translate `PackageMetadata` checksums into SPDX `Checksum` objects.

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

        Returns a `LicenseExpression` on success, `SpdxNoAssertion()`
        when the string is missing, an upstream `NOASSERTION` sentinel,
        or fails strict parsing. The validator rejects a literal
        `LicenseSymbol('NOASSERTION')`, so we hand back the typed
        `SpdxNoAssertion()` directly: same intent, validation-clean.
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
        """Assemble the SPDX `externalRefs` block.

        Always includes the package's primary purl. CPE strings (when
        provided) land as a security-category `cpe23Type` ref. Extra
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
        refs.extend(
            ExternalPackageRef(
                ExternalPackageRefCategory.PACKAGE_MANAGER,
                "purl",
                extra.to_string(),
            )
            for extra in metadata.extra_purls
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
        [SPDX package metadata specifications](https://spdx.github.io/spdx-spec/v2.3/package-information/).
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
        self.purl_index[package.purl.to_string()] = package_docid
        self._track_addition(manager.id, package.id, metadata)

        download_location = metadata.download_url or SpdxNoAssertion()
        homepage = metadata.homepage or None
        # SPDX requires `files_analyzed=True` only when the renderer also
        # emits per-file entries. We keep it `False` for inventory-level
        # snapshots: any extractor that captures file lists today (pip
        # `RECORD`, dpkg `.md5sums`) stores them in
        # `PackageMetadata.files`, but the SPDX File model is not wired
        # in yet. Promoting to `True` is safe to do later when that
        # writer lands.
        files_analyzed = metadata.files_analyzed

        license_concluded = self._license_or_noassertion(metadata.license_concluded)
        license_declared = self._license_or_noassertion(metadata.license_declared)
        copyright_text = metadata.copyright_text or None

        spdx_package = SPDXPackage(
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
        self.document.packages.append(spdx_package)
        self.package_by_docid[package_docid] = spdx_package

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
            self.pending_relationships.append((
                package_docid,
                manager.id,
                dep.target_id,
                rel_type,
            ))

        # Pull rich data from an upstream per-package SBOM if present.
        if metadata.external_sbom_path is not None:
            try:
                self._merge_external_sbom(
                    package_docid=package_docid,
                    package=package,
                    manager_id=manager.id,
                    sbom_path=metadata.external_sbom_path,
                )
            except Exception as exc:  # noqa: BLE001
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

        Brew formulae installed with `HOMEBREW_SBOM=1` write
        `<prefix>/sbom.spdx.json` per formula. The document carries the
        full upstream dependency closure with real download URLs, real
        checksums, real licenses. We adopt its child packages (transitive
        deps), prefix their SPDX IDs with the manager/formula namespace
        to avoid collisions, and re-wire relationship targets accordingly.

        The root package in the upstream file matches the formula we just
        added; we drop it from the merge (its slot in the aggregate doc
        is already taken by the entry the inventory pass produced) and
        rewire any relationships that pointed at it so they point at our
        already-emitted `package_docid`.

        Errors are caught one level up: a single malformed upstream file
        must not abort the entire scan.
        """
        with open(sbom_path, "rb") as fh:
            data = fh.read()
        digest = hashlib.sha1(data).hexdigest()
        upstream = json.loads(data)

        doc_ref_id = self.normalize_spdx_id(f"DocumentRef-{manager_id}-{package.id}")
        # SPDX IDs are matched textually. Keep the prefix terse but
        # collision-free across formulae sharing common dep names.
        local_prefix = self.normalize_spdx_id(f"SPDXRef-{manager_id}-{package.id}")
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

        # Record the upstream document for traceability. The
        # `documentNamespace` copied through from Homebrew points at
        # `https://formulae.brew.sh/spdx/<name>-<version>.json`, which
        # 404s because nothing is published there; tracked upstream at
        # https://github.com/Homebrew/brew/issues/22741. Carrying the
        # value verbatim keeps the aggregate document consistent with the
        # source files until that issue is resolved.
        self.merged_docs[doc_ref_id] = digest
        self.document.creation_info.external_document_refs.append(
            ExternalDocumentRef(
                document_ref_id=doc_ref_id,
                document_uri=upstream.get("documentNamespace") or f"file://{sbom_path}",
                checksum=SPDXChecksum(SPDXChecksumAlgorithm.SHA1, digest),
            )
        )

    def all_purls(self) -> Iterator[str]:
        """Yield every inventory package purl in insertion order.

        Only the directly-installed packages carry a purl in
        `purl_index`; transitive packages spliced in from merged
        upstream SBOMs are not queried for vulnerabilities (their own
        upstream document already carries that provenance, and they are
        not what the user installed).
        """
        yield from self.purl_index

    def finalize(self) -> None:
        """Emit pending dependency relationships and vulnerability refs.

        Walks the queue built by {meth}`add_package` and emits each
        relationship only when both ends resolve to packages we actually
        included in the document. Dangling references (the target package
        is not installed) are dropped silently: the SBOM only describes
        what is on the system, not what could be.

        Then attaches any vulnerability data bound via
        {meth}`attach_vulnerabilities`. SPDX 2.3 has no first-class
        vulnerability section, so each advisory becomes a
        SECURITY-category `ExternalPackageRef` of type `advisory` on
        the affected package, pointing at the advisory URL.
        """
        for source_docid, manager_id, target_id, rel_type in self.pending_relationships:
            target_docid = self.name_index.get((manager_id, target_id))
            if not target_docid:
                continue
            self.document.relationships.append(
                Relationship(target_docid, rel_type, source_docid)
            )

        for purl_str, vulns in self.vulnerabilities_by_purl.items():
            docid = self.purl_index.get(purl_str)
            if not docid:
                continue
            spdx_package = self.package_by_docid.get(docid)
            if spdx_package is None:
                continue
            for vuln in vulns:
                spdx_package.external_references.append(
                    ExternalPackageRef(
                        ExternalPackageRefCategory.SECURITY,
                        "advisory",
                        vuln.advisory_url,
                        comment=_vuln_comment(vuln),
                    )
                )

    def stats(self) -> dict[str, object]:
        """Extend the base stats with SPDX-specific counters.

        Adds the number of upstream documents merged into the aggregate,
        the count of transitive packages those upstream documents
        contributed (over and above the inventory pass), and the total
        relationship count partitioned into dependency vs descriptive
        edges. `packages_total` from the base reports inventory
        packages only; `packages_in_document` here is the full count
        after merge, which is what consumers of the file actually see.
        """
        base = super().stats()
        inventory_count = cast("int", base["packages_total"])
        in_doc = len(self.document.packages)
        dependency_count = sum(
            1
            for rel in self.document.relationships
            if "DEPENDENCY" in rel.relationship_type.name
        )
        base.update({
            "packages_in_document": in_doc,
            "transitive_packages_merged": in_doc - inventory_count,
            "merged_documents": len(self.merged_docs),
            "relationships_total": len(self.document.relationships),
            "dependency_relationships": dependency_count,
        })
        return base

    def export(self) -> str:
        """Similar to `spdx_tools.spdx.writer.write_anything.write_file` but write
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
