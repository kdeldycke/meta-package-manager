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

import pytest

from meta_package_manager.base import Operations
from meta_package_manager.sbom import SPDX, ExportFormat

from .test_cli import CLISubCommandTests


@pytest.fixture
def subcmd():
    # The details of operations are only logged at INFO level.
    return "--verbosity", "INFO", "sbom"


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

    def test_default_all_managers_spdx_output_to_console(self, invoke, subcmd):
        result = invoke(subcmd)
        assert result.exit_code == 0
        assert "Print SPDX export to <stdout>" in result.stderr
        self.check_manager_selection(result)

    @pytest.mark.parametrize("export_format", ExportFormat.values())
    @pytest.mark.parametrize("standard_name", ("SPDX", "CycloneDX"))
    def test_output_to_file(self, invoke, subcmd, export_format, standard_name):
        result = invoke(subcmd, f"--{standard_name.lower()}", "--format", export_format)

        if standard_name == "CycloneDX" and export_format not in (
            ExportFormat.JSON.value,
            ExportFormat.XML.value,
        ):
            assert result.exit_code == 2
            assert (
                f"CycloneDX does not support {ExportFormat.from_value(export_format)}"
                " format." in result.stderr
            )
            assert not result.stdout

        else:
            assert result.exit_code == 0
            assert f"Print {standard_name} export to <stdout>" in result.stderr
            assert result.exit_code == 0
            self.check_manager_selection(result)
