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
"""``mpm sbom`` CLI tests.

Drives the subcommand end to end: format resolution, per-standard exports to
console and file, the ``--query`` filter and ``--minimal`` mode. The SPDX and
CycloneDX renderers it delegates to are unit-tested in :mod:`tests.test_sbom`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from xml.etree import ElementTree

import pytest
from yaml import Loader, load

from meta_package_manager.capabilities import Operations
from meta_package_manager.sbom.base import ExportFormat

from .test_cli import CLISubCommandTests
from .test_sbom import assert_valid_cyclonedx


@pytest.fixture
def subcmd():
    # ``DEBUG`` level is required so that ``check_manager_selection`` can detect
    # skip/does-not-implement signals for implicitly selected managers. Those
    # messages are demoted to DEBUG when no explicit ``--<id>`` flag is passed
    # (to avoid flooding the output). INFO messages are a subset of DEBUG, so
    # everything logged at INFO still appears.
    return "--verbosity", "DEBUG", "sbom"


class TestSBOM(CLISubCommandTests):
    @staticmethod
    def evaluate_signals(mid, stdout, stderr):
        yield from (
            # The glued ``:<mid>:`` label form matches whatever level the
            # message lands at: demoted to DEBUG for implicit selection,
            # WARNING/INFO for explicit ones (``mpm --<mid> sbom``).
            f":{mid}: Export packages..." in stderr,
            f":{mid}: Does not implement {Operations.installed}" in stderr,
            f":{mid}: Skipped:" in stderr,
            f":{mid}: Could not list installed packages." in stderr,
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
        assert (
            "Use --format to pick one of: json, xml, yaml, tag, rdf." in result.stderr
        )
        # The collection loop must not have run.
        assert "Export packages from" not in result.stderr

    def test_unrecognized_extension_with_explicit_format(
        self, invoke, subcmd, tmp_path
    ):
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


def test_sbom_query_filter_narrows_to_matches(invoke, fake_pool):
    """``sbom --query`` keeps only installed packages matching the query."""
    result = invoke("sbom", "--query", "alpha", "--minimal")
    assert result.exit_code == 0
    assert "fake-pkg-alpha" in result.stdout
    assert "fake-pkg-beta" not in result.stdout


def test_sbom_without_query_lists_all(invoke, fake_pool):
    """Without a query, ``sbom`` exports the full installed inventory."""
    result = invoke("sbom", "--minimal")
    assert result.exit_code == 0
    assert "fake-pkg-alpha" in result.stdout
    assert "fake-pkg-beta" in result.stdout


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
