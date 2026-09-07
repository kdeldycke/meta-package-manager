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


DNF5_INSTALLED_EVR = (
    "librepo___MPM___1.21.0-1.fc44___MPM___Repodata downloading library"
    "___MPM___aarch64\n"
    "openldap___MPM___2.6.13-1.fc44___MPM___LDAP support libraries"
    "___MPM___aarch64\n"
    "wireless-regdb___MPM___2026.05.30-1.fc44___MPM___Regulatory database for"
    " 802.11 wireless networking___MPM___noarch\n"
)
"""`repoquery --installed`, the pass that supplies the version actually held."""

DNF5_UPGRADES = (
    "librepo___MPM___1.21.0-2.fc44___MPM___Repodata downloading library"
    "___MPM___aarch64\n"
    "openldap___MPM___2.6.14-1.fc44___MPM___LDAP support libraries"
    "___MPM___aarch64\n"
    "wireless-regdb___MPM___2026.09.03-1.fc44___MPM___Regulatory database for"
    " 802.11 wireless networking___MPM___noarch\n"
)
"""`repoquery --upgrades`, whose every field describes the *candidate*."""


DNF5_ORPHANS = (
    "bc-0:1.08.2-4.fc44.aarch64\n"
    "dos2unix-0:7.5.6-1.fc44.aarch64\n"
    "tree-0:2.2.1-4.fc44.aarch64\n"
)
"""`repoquery --unneeded` on Fedora 44, after `dnf mark dependency`.

A fresh host answers this query empty, having nothing installed as a
dependency and since abandoned, so the parser had never been fed a row until
three leaf packages were marked to make some.
"""


def test_orphans_parses_a_real_listing():
    """NEVRA rows carry an epoch the package id must not absorb.

    Every row here opens `name-0:` and the release ends in `.fc44`, so both the
    epoch and the dotted release sit between the id and the architecture.
    """
    found = [
        (
            match.group("package_id"),
            match.group("installed_version"),
            match.group("arch"),
        )
        for match in DNF._ORPHANS_REGEXP.finditer(DNF5_ORPHANS)
    ]
    assert found == [
        ("bc", "1.08.2-4.fc44", "aarch64"),
        ("dos2unix", "7.5.6-1.fc44", "aarch64"),
        ("tree", "2.2.1-4.fc44", "aarch64"),
    ]


def test_outdated_reports_the_installed_version(monkeypatch):
    """`outdated` must not read the candidate's own version as the installed one.

    `--upgrades` restricts the query to available packages, so a single call
    describes the candidate twice: `%{version}` and `%{evr}` are two renderings
    of it, never of what the host holds. Reading the first as `installed_version`
    reported `openldap 2.6.14` on a machine carrying `2.6.13-1.fc44`, and made
    the release-only `librepo` bump read as an upgrade between two identical
    versions.
    """
    manager = DNF5()

    def fake_run_cli(*args, **kwargs) -> str:
        return DNF5_INSTALLED_EVR if "--installed" in args else DNF5_UPGRADES

    monkeypatch.setattr(manager, "run_cli", fake_run_cli)

    found = {
        package.id: (str(package.installed_version), str(package.latest_version))
        for package in manager.outdated
    }
    assert found == {
        # A release-only rebuild: visible only because both sides are `%{evr}`.
        "librepo": ("1.21.0-1.fc44", "1.21.0-2.fc44"),
        "openldap": ("2.6.13-1.fc44", "2.6.14-1.fc44"),
        "wireless-regdb": ("2026.05.30-1.fc44", "2026.09.03-1.fc44"),
    }
    # Every row is a real upgrade, which is the property the old mapping lost.
    for installed, latest in found.values():
        assert parse_version(installed) < parse_version(latest)


def test_outdated_joins_on_name_and_architecture(monkeypatch):
    """A multilib host installs one name for two architectures.

    Joining on the name alone would hand the candidate whichever architecture
    happened to be read last.
    """
    manager = DNF5()
    installed = (
        "zlib___MPM___1.3.1-1.fc44___MPM___Compression library___MPM___x86_64\n"
        "zlib___MPM___1.3.0-1.fc44___MPM___Compression library___MPM___i686\n"
    )
    upgrades = "zlib___MPM___1.3.2-1.fc44___MPM___Compression library___MPM___i686\n"

    def fake_run_cli(*args, **kwargs) -> str:
        return installed if "--installed" in args else upgrades

    monkeypatch.setattr(manager, "run_cli", fake_run_cli)

    (package,) = list(manager.outdated)
    assert package.arch == "i686"
    assert str(package.installed_version) == "1.3.0-1.fc44"


def test_outdated_keeps_a_candidate_with_no_installed_match(monkeypatch):
    """A pending upgrade is reported even when its installed row is missing.

    Dropping the row would hide the upgrade outright, which is the worse of the
    two wrong answers.
    """
    manager = DNF5()

    def fake_run_cli(*args, **kwargs) -> str:
        return "" if "--installed" in args else DNF5_UPGRADES

    monkeypatch.setattr(manager, "run_cli", fake_run_cli)

    packages = list(manager.outdated)
    assert len(packages) == 3
    assert all(package.installed_version is None for package in packages)


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
