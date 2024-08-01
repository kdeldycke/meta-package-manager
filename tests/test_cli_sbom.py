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

import pytest

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
        ("export.rdf", ExportFormat.RDF_XML),
        ("export.rDf", ExportFormat.RDF_XML),
        ("export.rdf.random", None),
        ("exportrdf", None),
        ("export.rdf.xml", ExportFormat.RDF_XML),
        ("export.Rdf.xMl", ExportFormat.RDF_XML),
        ("export.rdf.xml.random", None),
        ("export.rdfxml", None),
        ("exportrdfxml", None),
        ("export.tag", ExportFormat.TAG_VALUE),
        ("export.tAg", ExportFormat.TAG_VALUE),
        ("export.tag.random", None),
        ("exporttag", None),
        ("export.spdx", ExportFormat.TAG_VALUE),
        ("export.sPdx", ExportFormat.TAG_VALUE),
        ("export.spdx.random", None),
        ("exportspdx", None),
        ("export.json", ExportFormat.JSON),
        ("export.jSon", ExportFormat.JSON),
        ("export.json.random", None),
        ("exportjson", None),
        ("export.xml", ExportFormat.XML),
        ("export.xMl", ExportFormat.XML),
        ("export.xml.random", None),
        ("exportxml", None),
        ("export.yaml", ExportFormat.YAML),
        ("export.yAml", ExportFormat.YAML),
        ("export.yaml.random", None),
        ("exportyaml", None),
        ("export.yml", ExportFormat.YAML),
        ("export.yMl", ExportFormat.YAML),
        ("export.yml.random", None),
        ("exportyml", None),
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

    @pytest.mark.parametrize(
        "output_file", ("-", *(f"export.{f}" for f in ExportFormat.values()))
    )
    @pytest.mark.parametrize("standard_name", ("SPDX", "CycloneDX"))
    def test_output_to_file(self, invoke, subcmd, output_file, standard_name):
        # Let the CLI auto-detect the format.
        result = invoke(subcmd, f"--{standard_name.lower()}", output_file)

        if standard_name == "CycloneDX" and output_file not in (
            "export.json",
            "export.xml",
            "-",
        ):
            assert result.exit_code == 2
            assert "CycloneDX does not support" in result.stderr
            assert not result.stdout

        else:
            if output_file == "-":
                assert f"Print {standard_name} export to <stdout>" in result.stderr
                assert result.stdout

            else:
                assert re.search(
                    rf"Export installed packages in {standard_name} to \S*{output_file}",
                    result.stderr,
                )
                assert not result.stdout

            assert result.exit_code == 0
            self.check_manager_selection(result)
