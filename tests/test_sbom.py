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

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import pytest

# The CycloneDX and SPDX writer stacks are optional (the [sbom-offline] extra),
# and their imports are guarded in meta_package_manager.sbom. Skip the whole
# module when they are absent so a hermetic packager build collects it cleanly
# instead of crashing on the direct writer imports below.
pytest.importorskip("cyclonedx")
pytest.importorskip("spdx_tools")

from cyclonedx.schema import OutputFormat, SchemaVersion
from cyclonedx.validation import make_schemabased_validator
from cyclonedx.validation.json import JsonStrictValidator

from meta_package_manager.manager import PackageManager
from meta_package_manager.package import (
    EMPTY_METADATA,
    Checksum,
    ChecksumAlgorithm,
    Dependency,
    DependencyScope,
    Originator,
    Package,
    PackageMetadata,
    Supplier,
)
from meta_package_manager.sbom.base import SBOM, ExportFormat
from meta_package_manager.sbom.cyclonedx import CycloneDX
from meta_package_manager.sbom.spdx import SPDX
from meta_package_manager.sbom.vulnerabilities import Vulnerability


class _StubManager:
    """Unit tests of the SBOM renderers and their shared base class.

    Hermetic: pure-function tests over duck-typed manager stubs, covering export
    format autodetection, the SPDX and CycloneDX writers, upstream-document
    merging, stats and vulnerability rendering. The `mpm sbom` command driving
    these renderers is exercised in {mod}`tests.test_cli_sbom`.
    """

    def __init__(self, manager_id: str, name: str) -> None:
        self.id = manager_id
        self.name = name


def _as_manager(stub: _StubManager) -> PackageManager:
    """Cast a duck-typed stub to the typed {class}`PackageManager` API.

    The SBOM renderers only read `id` and `name` from the manager, which is
    why instantiating real concrete managers (with CLI discovery, version
    parsing) is sidestepped here.
    """
    return cast("PackageManager", stub)


def _make_package(manager_id: str, package_id: str, version: str) -> Package:
    return Package(id=package_id, manager_id=manager_id, installed_version=version)


def assert_valid_cyclonedx(content: str, export_format: ExportFormat | str) -> None:
    """Assert a CycloneDX export validates against its schema.

    This guarantee used to live in
    {meth}`meta_package_manager.sbom.cyclonedx.CycloneDX.export` at runtime. It moved
    here so the `jsonschema`-based validation stack (`rfc3987-syntax`,
    `lark`, `lxml`) stays out of `mpm`'s runtime dependencies. See
    {mod}`meta_package_manager.sbom`.
    """
    validator: Any
    if export_format == ExportFormat.JSON:
        validator = JsonStrictValidator(SchemaVersion.V1_7)
    else:
        validator = make_schemabased_validator(OutputFormat.XML, SchemaVersion.V1_7)
    errors = validator.validate_str(content)
    assert not errors, f"Invalid CycloneDX {export_format} export: {errors}"


@pytest.mark.parametrize(
    ("file_path", "expected"),
    (
        # .json
        ("export.json", ExportFormat.JSON),
        ("export.jSon", ExportFormat.JSON),
        ("export.json.random", None),
        ("exportjson", None),
        (".json", None),
        # .xml
        ("export.xml", ExportFormat.XML),
        ("export.xMl", ExportFormat.XML),
        ("export.xml.random", None),
        ("exportxml", None),
        (".xml", None),
        # .yaml
        ("export.yaml", ExportFormat.YAML),
        ("export.yAml", ExportFormat.YAML),
        ("export.yaml.random", None),
        ("exportyaml", None),
        (".yaml", None),
        # .yml
        ("export.yml", ExportFormat.YAML),
        ("export.yMl", ExportFormat.YAML),
        ("export.yml.random", None),
        ("exportyml", None),
        (".yml", None),
        # .tag
        ("export.tag", ExportFormat.TAG_VALUE),
        ("export.tAg", ExportFormat.TAG_VALUE),
        ("export.tag.random", None),
        ("exporttag", None),
        (".tag", None),
        # .spdx
        ("export.spdx", ExportFormat.TAG_VALUE),
        ("export.sPdx", ExportFormat.TAG_VALUE),
        ("export.spdx.random", None),
        ("exportspdx", None),
        (".spdx", None),
        # .rdf
        ("export.rdf", ExportFormat.RDF_XML),
        ("export.rDf", ExportFormat.RDF_XML),
        ("export.rdf.random", None),
        ("exportrdf", None),
        (".rdf", None),
        # .rdf.xml
        ("export.rdf.xml", ExportFormat.RDF_XML),
        ("export.Rdf.xMl", ExportFormat.RDF_XML),
        ("export.rdf.xml.random", None),
        ("export.rdfxml", None),
        ("exportrdfxml", None),
        (".rdf.xml", ExportFormat.XML),
        # Unidentified extension
        ("export.random", None),
        ("export", None),
    ),
)
def test_file_autodetect(file_path, expected):
    assert SBOM.autodetect_export_format(Path(file_path)) == expected


@pytest.mark.parametrize(
    ("raw_str", "expected"),
    (
        ("SPDXRef-Package-brew-openjdk@11", "SPDXRef-Package-brew-openjdk-11"),
        ("SPDXRef-my.Super.package", "SPDXRef-my.Super.package"),
        ("SPDXRef-my---Super.package-------", "SPDXRef-my-Super.package"),
        (
            "pkg:alpm/arch/pacman@6.0.1-1?arch=x86_64",
            "pkg-alpm-arch-pacman-6.0.1-1-arch-x86-64",
        ),
        (
            "pkg:alpm/arch/containers-common@1:0.47.4-4?arch=x86_64",
            "pkg-alpm-arch-containers-common-1-0.47.4-4-arch-x86-64",
        ),
        (
            "pkg:bitnami/wordpress@6.2.0?arch=arm64&distro=debian-12",
            "pkg-bitnami-wordpress-6.2.0-arch-arm64-distro-debian-12",
        ),
        (
            "pkg:cocoapods/GoogleUtilities@7.5.2#NSData+zlib",
            "pkg-cocoapods-GoogleUtilities-7.5.2-NSData-zlib",
        ),
        (
            "pkg:deb/debian/curl@7.50.3-1?arch=i386&distro=jessie",
            "pkg-deb-debian-curl-7.50.3-1-arch-i386-distro-jessie",
        ),
    ),
)
def test_normalize_spdx_id(raw_str, expected):
    assert SPDX.normalize_spdx_id(raw_str) == expected


def _rich_metadata() -> PackageMetadata:
    """Realistic metadata used by the renderer-level tests below."""
    return PackageMetadata(
        download_url="https://curl.se/download/curl-8.9.0.tar.xz",
        homepage="https://curl.se",
        vcs_url="https://github.com/curl/curl",
        license_declared="MIT",
        license_concluded="MIT",
        supplier=Supplier(name="Homebrew Formulae", url="https://brew.sh"),
        originator=Originator(name="Daniel Stenberg", email="daniel@haxx.se"),
        description="HTTP transfer library",
        summary="HTTP transfer library",
        checksums=(Checksum(ChecksumAlgorithm.SHA256, "a" * 64),),
        dependencies=(Dependency(target_id="openssl", scope=DependencyScope.RUNTIME),),
    )


def test_minimal_mode_emits_bare_spdx_payload():
    """Minimal mode must reproduce the legacy bare output: rich
    metadata is ignored, no relationships beyond `DESCRIBES` are
    emitted, and `download_location` falls back to `NOASSERTION`.
    """
    s = SPDX()
    s.init_doc()
    manager = _as_manager(_StubManager("brew", "Homebrew Formulae"))
    pkg = _make_package("brew", "curl", "8.9.0")
    s.add_package(manager, pkg)  # No metadata, simulating minimal mode.
    s.finalize()
    doc = json.loads(s.export())
    package = doc["packages"][0]
    assert package["name"] == "curl"
    assert package["downloadLocation"] == "NOASSERTION"
    assert "licenseDeclared" not in package
    assert all(r["relationshipType"] == "DESCRIBES" for r in doc["relationships"])


def test_bundled_mode_spdx_populates_rich_fields():
    """A populated {class}`PackageMetadata` flows into the SPDX
    document: license, supplier override, originator, checksum, and a
    dependency relationship resolved at {meth}`finalize` time.
    """
    s = SPDX()
    s.init_doc()
    manager = _as_manager(_StubManager("brew", "Homebrew Formulae"))
    curl = _make_package("brew", "curl", "8.9.0")
    openssl = _make_package("brew", "openssl", "3.3.1")
    s.add_package(manager, curl, _rich_metadata())
    s.add_package(manager, openssl, EMPTY_METADATA)
    s.finalize()
    doc = json.loads(s.export())
    curl_pkg = next(p for p in doc["packages"] if p["name"] == "curl")
    assert curl_pkg["downloadLocation"].endswith("curl-8.9.0.tar.xz")
    assert curl_pkg["homepage"] == "https://curl.se"
    assert curl_pkg["licenseDeclared"] == "MIT"
    assert curl_pkg["checksums"][0]["algorithm"] == "SHA256"
    assert "Daniel Stenberg" in curl_pkg["originator"]
    rels = [r["relationshipType"] for r in doc["relationships"]]
    assert "RUNTIME_DEPENDENCY_OF" in rels


def test_bundled_mode_cyclonedx_populates_rich_fields():
    """CycloneDX renderer projects the same metadata into hashes,
    licenses, supplier, external references, and dependency edges.
    """
    c = CycloneDX()
    c.init_doc()
    manager = _as_manager(_StubManager("brew", "Homebrew Formulae"))
    curl = _make_package("brew", "curl", "8.9.0")
    openssl = _make_package("brew", "openssl", "3.3.1")
    c.add_package(manager, curl, _rich_metadata())
    c.add_package(manager, openssl, EMPTY_METADATA)
    c.finalize()
    doc = json.loads(c.export())
    curl_comp = next(comp for comp in doc["components"] if comp["name"] == "curl")
    assert curl_comp["hashes"][0]["alg"] == "SHA-256"
    assert curl_comp["licenses"][0]["license"]["id"] == "MIT"
    ref_types = {ref["type"] for ref in curl_comp["externalReferences"]}
    assert "website" in ref_types
    assert "vcs" in ref_types
    deps_for_curl = next(
        dep for dep in doc["dependencies"] if dep["ref"] == curl.purl.to_string()
    )
    assert openssl.purl.to_string() in deps_for_curl["dependsOn"]
    assert_valid_cyclonedx(c.export(), ExportFormat.JSON)


@pytest.mark.parametrize(
    ("expression", "expected_identifiers"),
    (
        # Two-license compound expression.
        ("MIT AND Apache-2.0", ("Apache-2.0", "MIT")),
        # License combined with an SPDX exception via WITH.
        (
            "MIT WITH Classpath-exception-2.0",
            ("Classpath-exception-2.0", "MIT"),
        ),
        # Nested parenthesized expression with three identifiers.
        (
            "MIT OR (Apache-2.0 AND BSD-3-Clause)",
            ("Apache-2.0", "BSD-3-Clause", "MIT"),
        ),
        # Duplicates in the source collapse to a single `details` entry.
        ("MIT AND MIT", ("MIT",)),
    ),
)
def test_cyclonedx_compound_license_expression_details(
    expression, expected_identifiers
):
    """Compound expressions emit `LicenseExpression.details` with a
    canonical SPDX URL per identifier, deduped and sorted by identifier.
    """
    c = CycloneDX()
    c.init_doc()
    manager = _as_manager(_StubManager("brew", "Homebrew Formulae"))
    pkg = _make_package("brew", "curl", "8.9.0")
    md = PackageMetadata(license_declared=expression, license_concluded=expression)
    c.add_package(manager, pkg, md)
    c.finalize()
    doc = json.loads(c.export())
    license_obj = doc["components"][0]["licenses"][0]
    assert license_obj["expression"] == expression
    details = license_obj["expressionDetails"]
    assert tuple(d["licenseIdentifier"] for d in details) == expected_identifiers
    assert tuple(d["url"] for d in details) == tuple(
        f"https://spdx.org/licenses/{ident}.html" for ident in expected_identifiers
    )
    assert_valid_cyclonedx(c.export(), ExportFormat.JSON)


@pytest.mark.parametrize(
    ("declared", "expected_present"),
    (
        # Plain SPDX IDs survive as-is.
        ("MIT", True),
        ("Apache-2.0", True),
        # NOASSERTION sentinels collapse to the typed singleton.
        ("NOASSERTION", False),
        # Free-text licenses tend to fail strict parsing — they fall back
        # to NOASSERTION rather than tripping the validator.
        ("Some custom license text the parser will reject", False),
        # LicenseRef-* without an extracted-license declaration is the
        # exact failure mode that Homebrew's per-formula SBOMs exposed.
        # It must also collapse to NOASSERTION to keep the doc valid.
        ("LicenseRef-Homebrew-public-domain", False),
        # Compound expressions stay if every symbol is known.
        ("MIT AND Apache-2.0", True),
    ),
)
def test_spdx_license_normalization(declared, expected_present):
    """The SPDX renderer must produce a document that validates against
    the SPDX schema for every input it accepts.
    """
    s = SPDX()
    s.init_doc()
    md = PackageMetadata(license_declared=declared)
    s.add_package(
        _as_manager(_StubManager("brew", "Homebrew Formulae")),
        _make_package("brew", "curl", "8.9.0"),
        md,
    )
    s.finalize()
    doc = json.loads(s.export())  # exporting also validates the doc.
    pkg = doc["packages"][0]
    if expected_present:
        assert pkg["licenseDeclared"] == declared
    else:
        assert pkg.get("licenseDeclared") in (None, "NOASSERTION")


def test_spdx_merges_external_per_package_sbom(tmp_path):
    """The renderer adopts transitive deps from a per-package upstream
    SPDX file and records the merge in `externalDocumentRefs`.

    The fixture mirrors the shape of Homebrew's
    `<prefix>/Cellar/<formula>/<version>/sbom.spdx.json`.
    """
    upstream = {
        "SPDXID": "SPDXRef-DOCUMENT",
        "spdxVersion": "SPDX-2.3",
        "documentNamespace": "https://example.org/sbom/curl-8.9.0",
        "documentDescribes": ["SPDXRef-Package-curl"],
        "packages": [
            {
                "SPDXID": "SPDXRef-Package-curl",
                "name": "curl",
                "versionInfo": "8.9.0",
                "downloadLocation": "https://curl.se/download/curl-8.9.0.tar.xz",
                "licenseDeclared": "MIT",
                "homepage": "https://curl.se",
            },
            {
                "SPDXID": "SPDXRef-Package-zlib",
                "name": "zlib",
                "versionInfo": "1.3",
                "downloadLocation": "https://zlib.net/zlib-1.3.tar.gz",
                "licenseDeclared": "Zlib",
            },
        ],
        "relationships": [
            {
                "spdxElementId": "SPDXRef-Package-curl",
                "relationshipType": "DEPENDS_ON",
                "relatedSpdxElement": "SPDXRef-Package-zlib",
            }
        ],
    }
    sbom_file = tmp_path / "sbom.spdx.json"
    sbom_file.write_text(json.dumps(upstream))
    md = PackageMetadata(external_sbom_path=sbom_file)
    s = SPDX()
    s.init_doc()
    s.add_package(
        _as_manager(_StubManager("brew", "Homebrew Formulae")),
        _make_package("brew", "curl", "8.9.0"),
        md,
    )
    s.finalize()
    doc = json.loads(s.export())
    names = sorted(p["name"] for p in doc["packages"])
    assert names == ["curl", "zlib"]
    edrs = doc.get("externalDocumentRefs") or []
    assert len(edrs) == 1
    assert edrs[0]["checksum"]["algorithm"] == "SHA1"


def test_stats_track_per_manager_and_merge_counts(tmp_path):
    """`SBOM.stats()` must reflect what landed in the document.

    Two packages from a single manager land normally; one of them
    carries an external SBOM file containing one transitive dep, which
    gets spliced in. The SPDX-specific stats then report:
    inventory=2, in_document=3, merged_documents=1.
    """
    upstream = {
        "SPDXID": "SPDXRef-DOCUMENT",
        "spdxVersion": "SPDX-2.3",
        "documentNamespace": "https://example.org/sbom/curl-8.9.0",
        "documentDescribes": ["SPDXRef-Package-curl"],
        "packages": [
            {
                "SPDXID": "SPDXRef-Package-curl",
                "name": "curl",
                "versionInfo": "8.9.0",
                "downloadLocation": "NOASSERTION",
            },
            {
                "SPDXID": "SPDXRef-Package-zlib",
                "name": "zlib",
                "versionInfo": "1.3",
                "downloadLocation": "NOASSERTION",
            },
        ],
        "relationships": [
            {
                "spdxElementId": "SPDXRef-Package-curl",
                "relationshipType": "DEPENDS_ON",
                "relatedSpdxElement": "SPDXRef-Package-zlib",
            }
        ],
    }
    sbom_file = tmp_path / "sbom.spdx.json"
    sbom_file.write_text(json.dumps(upstream))

    s = SPDX()
    s.init_doc()
    manager = _as_manager(_StubManager("brew", "Homebrew Formulae"))
    s.add_package(
        manager,
        _make_package("brew", "curl", "8.9.0"),
        PackageMetadata(
            external_sbom_path=sbom_file,
            license_declared="MIT",
        ),
    )
    s.add_package(
        manager,
        _make_package("brew", "openssl", "3.3.1"),
        EMPTY_METADATA,
    )
    s.finalize()

    stats = s.stats()
    assert stats["packages_total"] == 2
    assert stats["packages_per_manager"] == {"brew": 2}
    assert stats["enriched_per_manager"] == {"brew": 1}
    assert stats["packages_in_document"] == 3
    assert stats["transitive_packages_merged"] == 1
    assert stats["merged_documents"] == 1


def test_cyclonedx_stats_count_external_bom_refs(tmp_path):
    """CycloneDX stats report external BOM refs and dependency edges."""
    sbom_file = tmp_path / "sbom.spdx.json"
    sbom_file.write_text("{}")
    c = CycloneDX()
    c.init_doc()
    manager = _as_manager(_StubManager("brew", "Homebrew Formulae"))
    c.add_package(
        manager,
        _make_package("brew", "curl", "8.9.0"),
        PackageMetadata(
            external_sbom_path=sbom_file,
            dependencies=(Dependency(target_id="zlib"),),
        ),
    )
    c.add_package(
        manager,
        _make_package("brew", "zlib", "1.3"),
        EMPTY_METADATA,
    )
    c.finalize()

    stats = c.stats()
    assert stats["packages_total"] == 2
    assert stats["external_bom_references"] == 1
    assert cast("int", stats["dependency_edges"]) >= 1


def _sample_vulnerability():
    """Build a sample `Vulnerability` for the render tests."""
    return Vulnerability(
        id="GHSA-aaaa-bbbb-cccc",
        source="OSV",
        summary="XSS in example",
        description="Long detail.",
        severity="critical",
        cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        cwe_ids=("CWE-79",),
        aliases=("CVE-2021-99999",),
        references=("https://example.com/advisory",),
        fixed_versions=("1.0.1",),
        published_date=datetime(2021, 1, 1, tzinfo=timezone.utc),
        modified_date=datetime(2021, 6, 1, tzinfo=timezone.utc),
        advisory_url="https://osv.dev/vulnerability/GHSA-aaaa-bbbb-cccc",
    )


def test_spdx_renders_attached_vulnerabilities():
    """Attached advisories become SECURITY external refs in SPDX."""
    s = SPDX()
    s.init_doc()
    manager = _as_manager(_StubManager("pip", "Python pip"))
    package = _make_package("pip", "django", "1.0.0")
    s.add_package(manager, package, EMPTY_METADATA)
    purl = package.purl.to_string()
    s.attach_vulnerabilities({purl: (_sample_vulnerability(),)})
    s.finalize()
    doc = json.loads(s.export())  # exporting also validates the document.
    django = next(p for p in doc["packages"] if p["name"] == "django")
    security_refs = [
        ref
        for ref in django.get("externalRefs", [])
        if ref["referenceCategory"] == "SECURITY" and ref["referenceType"] == "advisory"
    ]
    assert len(security_refs) == 1
    assert "GHSA-aaaa-bbbb-cccc" in security_refs[0]["referenceLocator"]
    assert s.stats()["vulnerabilities_total"] == 1
    assert s.stats()["vulnerable_packages"] == 1


def test_cyclonedx_renders_attached_vulnerabilities():
    """Attached advisories become a CycloneDX vulnerabilities array entry."""
    c = CycloneDX()
    c.init_doc()
    manager = _as_manager(_StubManager("pip", "Python pip"))
    package = _make_package("pip", "django", "1.0.0")
    c.add_package(manager, package, EMPTY_METADATA)
    purl = package.purl.to_string()
    c.attach_vulnerabilities({purl: (_sample_vulnerability(),)})
    c.finalize()
    content = c.export()
    assert_valid_cyclonedx(content, ExportFormat.JSON)
    doc = json.loads(content)
    vulns = doc.get("vulnerabilities", [])
    assert len(vulns) == 1
    assert vulns[0]["id"] == "GHSA-aaaa-bbbb-cccc"
    affects = {target["ref"] for target in vulns[0]["affects"]}
    assert affects == {purl}
    assert vulns[0]["ratings"][0]["severity"] == "critical"


def test_shared_advisory_deduplicated_in_cyclonedx():
    """One advisory affecting two components yields a single record with
    two affects targets."""
    c = CycloneDX()
    c.init_doc()
    manager = _as_manager(_StubManager("pip", "Python pip"))
    django = _make_package("pip", "django", "1.0.0")
    flask = _make_package("pip", "flask", "2.0.0")
    c.add_package(manager, django, EMPTY_METADATA)
    c.add_package(manager, flask, EMPTY_METADATA)
    vuln = _sample_vulnerability()
    c.attach_vulnerabilities({
        django.purl.to_string(): (vuln,),
        flask.purl.to_string(): (vuln,),
    })
    c.finalize()
    doc = json.loads(c.export())
    vulns = doc.get("vulnerabilities", [])
    assert len(vulns) == 1
    affects = {target["ref"] for target in vulns[0]["affects"]}
    assert affects == {django.purl.to_string(), flask.purl.to_string()}
