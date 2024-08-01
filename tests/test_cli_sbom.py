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
from yaml import Loader, load

from meta_package_manager.base import Operations
from meta_package_manager.sbom import SBOM, SPDX, ExportFormat

from .test_cli import CLISubCommandTests


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
            f"Export packages from {mid}..." in stderr,
            f"warning: {mid} does not implement {Operations.installed}" in stderr,
            # Common "not found" message.
            f"info: Skip unavailable {mid} manager." in stderr,
        )

    def test_default_spdx_json_output_to_console(self, invoke, subcmd):
        result = invoke(subcmd)
        assert result.exit_code == 0
        assert "Print SPDX export to <stdout>" in result.stderr
        self.check_manager_selection(result)
        json_content = json.loads(result.stdout)
        assert json_content
        assert json_content["spdxVersion"] == "SPDX-2.3"

    @pytest.mark.parametrize("export_format", (None, *ExportFormat))
    @pytest.mark.parametrize("standard_name", ("SPDX", "CycloneDX"))
    def test_output_to_file(self, invoke, subcmd, export_format, standard_name):
        # Let the CLI auto-detect the format.
        file_name = f"export.{export_format.value}" if export_format else "-"
        result = invoke(subcmd, f"--{standard_name.lower()}", file_name)

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
                content = Path(file_name).read_text()

            assert result.exit_code == 0
            self.check_manager_selection(result)

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
                    assert xml_content.find("spdxVersion").text == "SPDX-2.3"
                else:
                    assert xml_content.tag == "{http://cyclonedx.org/schema/bom/1.6}bom"

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
                assert (
                    ElementTree.fromstring(content)
                    .find(
                        "spdx:SpdxDocument/spdx:specVersion",
                        {"spdx": "http://spdx.org/rdf/terms#"},
                    )
                    .text
                    == "SPDX-2.3"
                )
