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
"""RPM front-end tests, covering the Fedora 41 cutover to dnf5.

Every payload below is captured output, from Fedora Linux 44 Server aarch64
running dnf5 `5.4.3.0` and the dnf4 `4.24.0` that still ships beside it as
`/usr/bin/dnf4`. That host is the point: it carries `dnf`, `dnf5`, `yum` and
`microdnf` as four names for one dnf5 binary, which is the arrangement every
Fedora since 41 presents and which no CI runner reproduces.
"""

from __future__ import annotations

import re

import pytest

from meta_package_manager.managers.dnf import DNF, DNF5, YUM
from meta_package_manager.version import TokenizedString, VersionRange, parse_version

DNF5_VERSION = """dnf5 version 5.4.3.0
dnf5 plugin API version 2.0
libdnf5 version 5.4.3.0
libdnf5 plugin API version 2.2
"""
"""`dnf5 --version`, which `dnf`, `yum` and `microdnf` all answer on Fedora 44.

The banner opens with the tool's own name. The default `(?P<version>\\S+)`
regex reads that first token, so every RPM front-end reported its version as
the string `dnf5`, failed its own requirement and left the pool.
"""

DNF4_VERSION = """4.24.0
  Installed: rpm-0:6.0.2-1.fc44.aarch64 at Fri 04 Sep 2026 08:23:20 AM GMT
  Built    : Fedora Project at Thu 16 Jul 2026 04:13:23 PM GMT
"""
"""`dnf4 --version`: a bare version, the shape `dnf` itself has on RHEL 8 and 9."""

DNF5_SEARCH = (
    "Matched fields: name (exact)\n"
    " bash.aarch64\tThe GNU Bourne Again shell\n"
    "Matched fields: name, summary\n"
    " argbash.noarch\tBash argument parsing code generator\n"
    " bash-argsparse.noarch\tAn high level argument parsing library for bash\n"
)
"""`dnf --color=never --quiet search bash` on dnf5.

Three departures from dnf4 at once: the hit is indented, its two fields are
separated by a tab rather than by `" : "`, and the section headers are prose
instead of `===` rules.
"""

DNF4_SEARCH = (
    "Last metadata expiration check: 0:06:37 ago on Sun 03 Apr 2022.\n"
    "=================== Name Exactly Matched: usd =====================\n"
    "usd.aarch64 : 3D VFX pipeline interchange file format\n"
    "=================== Name & Summary Matched: usd ===================\n"
    "python3-usd.aarch64 : Development files for USD\n"
)
"""The dnf4 shape, kept so one parser is held to both."""


def probe_version(cls: type[DNF], output: str) -> TokenizedString | None:
    """Reproduce the version probe: first matching regex wins."""
    for regex in cls.version_regexes:
        match = re.compile(regex, re.MULTILINE).search(output)
        if match and match.groupdict().get("version"):
            return parse_version(match.groupdict()["version"])
    return None


@pytest.mark.parametrize(
    ("manager_class", "output", "expected_version", "expected_fresh"),
    (
        # The regression: dnf5 read as `dnf5` took Fedora's own manager out of
        # the pool with "version dnf5 does not satisfy '>=5.0.0' requirement".
        pytest.param(DNF5, DNF5_VERSION, "5.4.3.0", True, id="dnf5-on-dnf5"),
        # `dnf` is dnf5 on Fedora 41+, and `cli_path` stops at the first name it
        # finds without consulting the version. The ceiling is what makes this
        # class decline that binary, and decline it by its real version.
        pytest.param(DNF, DNF5_VERSION, "5.4.3.0", False, id="dnf-handed-dnf5"),
        pytest.param(DNF, DNF4_VERSION, "4.24.0", True, id="dnf-on-dnf4"),
        # `yum` fronts either generation, so it must accept both.
        pytest.param(YUM, DNF5_VERSION, "5.4.3.0", True, id="yum-on-dnf5"),
        pytest.param(YUM, DNF4_VERSION, "4.24.0", True, id="yum-on-dnf4"),
    ),
)
def test_version_probe_reads_both_generations(
    manager_class, output, expected_version, expected_fresh
):
    """Each front-end reads a real version, and gates itself on that version."""
    version = probe_version(manager_class, output)
    assert version is not None
    assert str(version) == expected_version
    fresh = version in VersionRange(manager_class.requirement)
    assert fresh is expected_fresh


@pytest.mark.parametrize(
    ("output", "expected"),
    (
        pytest.param(
            DNF5_SEARCH,
            (
                ("bash", "The GNU Bourne Again shell"),
                ("argbash", "Bash argument parsing code generator"),
                (
                    "bash-argsparse",
                    "An high level argument parsing library for bash",
                ),
            ),
            id="dnf5",
        ),
        pytest.param(
            DNF4_SEARCH,
            (
                ("usd", "3D VFX pipeline interchange file format"),
                ("python3-usd", "Development files for USD"),
            ),
            id="dnf4",
        ),
    ),
)
def test_search_parses_both_output_shapes(output, expected):
    """One regex covers dnf4 and dnf5, headers included.

    dnf5 returned nothing at all before: its tab-separated, indented hits match
    neither the `" : "` separator the pattern required nor an anchor placed at
    the first character. The descriptions are asserted whole because the
    pattern used to end on `\\S+`, storing every summary as its own first word.
    """
    hits = tuple(
        (match.group("package_id"), match.group("description"))
        for match in (DNF._SEARCH_REGEXP.match(line) for line in output.splitlines())
        if match
    )
    assert hits == expected


@pytest.mark.parametrize(
    "line",
    (
        pytest.param("Matched fields: name (exact)", id="dnf5-header"),
        pytest.param("Matched fields: name, summary", id="dnf5-header-summary"),
        pytest.param(
            "=================== Name Exactly Matched: usd =====================",
            id="dnf4-rule",
        ),
        pytest.param(
            "Last metadata expiration check: 0:06:37 ago on Sun 03 Apr 2022.",
            id="dnf4-banner",
        ),
        pytest.param("", id="blank"),
    ),
)
def test_search_rejects_non_package_lines(line):
    """Neither binary's chrome may be mistaken for a package.

    The parser dropped these by skipping the first line and any line opening on
    `=`, which covered dnf4 by construction and dnf5 by luck. Requiring a dotted
    `name.arch` token is what covers both.
    """
    assert DNF._SEARCH_REGEXP.match(line) is None
