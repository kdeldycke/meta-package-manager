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
import re
from pathlib import Path
from xml.etree import ElementTree

import pytest
from cyclonedx.schema import OutputFormat, SchemaVersion
from cyclonedx.validation import make_schemabased_validator
from cyclonedx.validation.json import JsonStrictValidator
from yaml import Loader, load

from meta_package_manager.capabilities import Operations
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
from meta_package_manager.sbom import SBOM, SPDX, CycloneDX, ExportFormat

from .test_cli import CLISubCommandTests


class _StubManager:
    """Lightweight stand-in for :py:class:`PackageManager`.

    Tests only need the two attributes the renderer reads.
    """

    def __init__(self, manager_id: str, name: str) -> None:
        self.id = manager_id
        self.name = name


def _make_package(manager_id: str, package_id: str, version: str) -> Package:
    return Package(
        id=package_id, manager_id=manager_id, installed_version=version
    )


def assert_valid_cyclonedx(content: str, export_format: ExportFormat) -> None:
    """Assert a CycloneDX export validates against its schema.

    This guarantee used to live in
    :py:meth:`meta_package_manager.sbom.CycloneDX.export` at runtime. It moved
    here so the ``jsonschema``-based validation stack (``rfc3987-syntax``,
    ``lark``, ``lxml``) stays out of ``mpm``'s runtime dependencies. See
    :py:mod:`meta_package_manager.sbom`.
    """
    if export_format == ExportFormat.JSON:
        validator = JsonStrictValidator(SchemaVersion.V1_7)
    else:
        validator = make_schemabased_validator(OutputFormat.XML, SchemaVersion.V1_7)
    errors = validator.validate_str(content)
    assert not errors, f"Invalid CycloneDX {export_format} export: {errors}"


@pytest.fixture
def subcmd():
    # The details of operations are only logged at INFO level.
    return "--verbosity", "INFO", "sbom"


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


class TestSBOM(CLISubCommandTests):
    @staticmethod
    def evaluate_signals(mid, stdout, stderr):
        yield from (
            # Log-level prefix is omitted because Skip/does-not-implement are
            # demoted to DEBUG for implicit selection and stay at WARNING/INFO
            # for explicit ones (``mpm --<mid> sbom``).
            f"Export packages from {mid}..." in stderr,
            f"{mid} does not implement {Operations.installed}" in stderr,
            f"Skip {mid} manager:" in stderr,
            f"Could not export packages from {mid}." in stderr,
        )

    def test_default_spdx_json_output_to_console(self, invoke, subcmd):
        # ``--verbosity DEBUG`` makes the per-manager skip/does-not-implement
        # messages reach stderr: at default verbosity they stay quiet because
        # this invocation makes no explicit ``--<id>`` selection.
        result = invoke("--verbosity", "DEBUG", subcmd)
        assert result.exit_code == 0
        assert "Print SPDX export to <stdout>" in result.stderr
        self.check_manager_selection(result)
        json_content = json.loads(result.stdout)
        assert json_content
        assert json_content["spdxVersion"] == "SPDX-2.3"

    def test_unrecognized_extension_without_format(self, invoke, subcmd):
        """A target path with no recognized extension must fail before any
        package collection happens, with an actionable message pointing at
        ``--format``.
        """
        result = invoke(subcmd, "help")
        assert result.exit_code == 2
        assert "Cannot guess export format from 'help'" in result.stderr
        assert "Use --format to pick one of: json, xml, yaml, tag, rdf." in result.stderr
        # The collection loop must not have run.
        assert "Export packages from" not in result.stderr

    def test_unrecognized_extension_with_explicit_format(self, invoke, subcmd, tmp_path):
        """An explicit ``--format`` overrides extension auto-detection, even when
        the filename carries no recognizable suffix.
        """
        target = tmp_path / "help"
        result = invoke(subcmd, "--format", "json", str(target))
        assert result.exit_code == 0
        json_content = json.loads(target.read_text(encoding="utf-8"))
        assert json_content["spdxVersion"] == "SPDX-2.3"

    @pytest.mark.parametrize("export_format", (None, *ExportFormat))
    @pytest.mark.parametrize("standard_name", ("SPDX", "CycloneDX"))
    def test_output_to_file(self, invoke, subcmd, export_format, standard_name):
        # Let the CLI auto-detect the format. ``--verbosity DEBUG`` makes the
        # per-manager skip messages reach stderr for check_manager_selection.
        file_name = f"export.{export_format.value}" if export_format else "-"
        result = invoke(
            "--verbosity", "DEBUG", subcmd, f"--{standard_name.lower()}", file_name
        )

        if standard_name == "CycloneDX" and export_format not in (
            ExportFormat.JSON,
            ExportFormat.XML,
            None,
        ):
            assert result.exit_code == 2
            assert f"CycloneDX does not support {export_format}" in result.stderr
            assert not result.stdout

        else:
            if not export_format:
                assert f"Print {standard_name} export to <stdout>" in result.stderr
                assert result.stdout
                content = result.stdout

            else:
                assert re.search(
                    rf"Export installed packages in {standard_name} to \S*{file_name}",
                    result.stderr,
                )
                assert not result.stdout
                content = Path(file_name).read_text(encoding="utf-8")

            assert result.exit_code == 0
            self.check_manager_selection(result)

            if standard_name == "CycloneDX" and export_format in (
                ExportFormat.JSON,
                ExportFormat.XML,
            ):
                assert_valid_cyclonedx(content, export_format)

            if export_format == ExportFormat.JSON:
                json_content = json.loads(content)
                assert json_content
                if standard_name == "SPDX":
                    assert json_content["spdxVersion"] == "SPDX-2.3"
                else:
                    assert json_content["bomFormat"] == "CycloneDX"

            elif export_format == ExportFormat.XML:
                xml_content = ElementTree.fromstring(content)
                if standard_name == "SPDX":
                    spdx_elem = xml_content.find("spdxVersion")
                    assert spdx_elem is not None
                    assert spdx_elem.text == "SPDX-2.3"
                else:
                    assert xml_content.tag == "{http://cyclonedx.org/schema/bom/1.7}bom"

            elif export_format == ExportFormat.YAML:
                yaml_content = load(content, Loader=Loader)
                assert yaml_content
                assert yaml_content["spdxVersion"] == "SPDX-2.3"

            elif export_format == ExportFormat.TAG_VALUE:
                assert content.splitlines()[:2] == [
                    "## Document Information",
                    "SPDXVersion: SPDX-2.3",
                ]

            elif export_format == ExportFormat.RDF_XML:
                rdf_elem = ElementTree.fromstring(content).find(
                    "spdx:SpdxDocument/spdx:specVersion",
                    {"spdx": "http://spdx.org/rdf/terms#"},
                )
                assert rdf_elem is not None
                assert rdf_elem.text == "SPDX-2.3"


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
    metadata is ignored, no relationships beyond ``DESCRIBES`` are
    emitted, and ``download_location`` falls back to ``NOASSERTION``.
    """
    s = SPDX()
    s.init_doc()
    s.set_scan_completeness(bundled=False)
    manager = _StubManager("brew", "Homebrew Formulae")
    pkg = _make_package("brew", "curl", "8.9.0")
    s.add_package(manager, pkg)  # No metadata, simulating minimal mode.
    s.finalize()
    doc = json.loads(s.export())
    package = doc["packages"][0]
    assert package["name"] == "curl"
    assert package["downloadLocation"] == "NOASSERTION"
    assert "licenseDeclared" not in package
    assert all(
        r["relationshipType"] == "DESCRIBES" for r in doc["relationships"]
    )


def test_bundled_mode_spdx_populates_rich_fields():
    """A populated :py:class:`PackageMetadata` flows into the SPDX
    document: license, supplier override, originator, checksum, and a
    dependency relationship resolved at :py:meth:`finalize` time.
    """
    s = SPDX()
    s.init_doc()
    s.set_scan_completeness(bundled=True)
    manager = _StubManager("brew", "Homebrew Formulae")
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
    c.set_scan_completeness(bundled=True)
    manager = _StubManager("brew", "Homebrew Formulae")
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
    s.set_scan_completeness(bundled=True)
    md = PackageMetadata(license_declared=declared)
    s.add_package(_StubManager("brew", "Homebrew Formulae"), _make_package("brew", "curl", "8.9.0"), md)
    s.finalize()
    doc = json.loads(s.export())  # exporting also validates the doc.
    pkg = doc["packages"][0]
    if expected_present:
        assert pkg["licenseDeclared"] == declared
    else:
        assert pkg.get("licenseDeclared") in (None, "NOASSERTION")


def test_spdx_merges_external_per_package_sbom(tmp_path):
    """The renderer adopts transitive deps from a per-package upstream
    SPDX file and records the merge in ``externalDocumentRefs``.

    The fixture mirrors the shape of Homebrew's
    ``<prefix>/Cellar/<formula>/<version>/sbom.spdx.json``.
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
    s.set_scan_completeness(bundled=True)
    s.add_package(
        _StubManager("brew", "Homebrew Formulae"),
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
    """``SBOM.stats()`` must reflect what landed in the document.

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
    s.set_scan_completeness(bundled=True)
    manager = _StubManager("brew", "Homebrew Formulae")
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
    c.set_scan_completeness(bundled=True)
    manager = _StubManager("brew", "Homebrew Formulae")
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
    assert stats["dependency_edges"] >= 1


def test_minimal_mode_skips_metadata_extractor(invoke):
    """``--minimal`` must avoid the rich-metadata code path so the
    export matches the historical bare shape even for managers that
    implement an extractor (Homebrew, pip).
    """
    result = invoke("sbom", "--minimal")
    assert result.exit_code == 0
    if not result.stdout.lstrip().startswith("{"):
        return
    doc = json.loads(result.stdout)
    for package in doc.get("packages", []):
        assert package["downloadLocation"] == "NOASSERTION"
        assert "licenseDeclared" not in package
        assert "checksums" not in package
