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

from meta_package_manager.sbom import SPDX


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
