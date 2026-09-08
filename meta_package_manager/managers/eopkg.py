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

import re
from html import unescape

from extra_platforms import LINUX_LIKE

from ..capabilities import search_capabilities, version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class EOPKG(PackageManager):
    """Solus' eopkg package manager, a PiSi fork.

    `installed` and `outdated` parse eopkg's fixed-width, `|`-delimited
    status table; the column regex requires that pipe structure, so the header
    and `===` separator rows fall through. `--no-color` is forced to keep
    the output free of ANSI escapes.

    Mutating operations pass `--yes-all` to auto-confirm eopkg's prompts so
    they run unattended.

    ```{note}
    eopkg `4.x` and `5.x` ship as a [Nuitka](https://nuitka.net) onefile bundle,
    and the Python each carries reads its stdout encoding from the locale alone.
    Under `C` or `POSIX` that encoding is `ascii`. The first summary holding a
    character it cannot encode then aborts the command with
    `Error: System error. Program terminated.` and exit `1`, after a truncated
    listing. `list-upgrades` and `list-available` write every summary raw, so
    either `Cap’n Proto` or `ImageMagick®` stops them; `search` escapes `®` but
    not `’`, so only the first stops it.

    No `extra_env` pins the locale here, because mpm never reaches that state.
    [PEP 538](https://peps.python.org/pep-0538/) coercion exports
    `LC_CTYPE=C.UTF-8` from mpm's own interpreter, and eopkg inherits it. A
    shell exports nothing, which is why the same command fails by hand and
    works through mpm. Measured on Solus `4.9`, against eopkg `4.4.0` and
    `5.0.0` alike.
    ```
    """

    name = "Solus eopkg"

    homepage_url = "https://github.com/getsolus/eopkg/"
    logo = "solus"

    keywords = ("solus",)

    platforms = LINUX_LIKE

    default_sudo = True

    requirement = ">=3.2.0"

    pre_args = ("--no-color",)

    _LIST_REGEXP = re.compile(
        r"^(?P<package_id>\S+)\s+\|.+?\|\s*(?P<installed_version>\S+)"
        r"\s*\|.+?\|.+?\|.+$",
    )
    _UPGRADE_REGEXP = re.compile(
        r"^(?P<package_id>\S+)\s+\|.+?\|\s*(?P<version>\S+)"
        r"\s*\|\s*(?P<release>\S+)\s*\|.+?\|.+$",
    )
    """{attr}`_LIST_REGEXP` with the `Rel.` column captured too.

    The two cannot be one pattern: {meth}`parse_regex_lines` maps every named
    group onto a package field, and `release` is not one of them.
    """
    _CANDIDATE_REGEXP = re.compile(
        r"^Package found in .+ repository:\n"
        r"Name\s*:\s*(?P<package_id>[^,]+),\s*version:\s*(?P<version>[^,]+),"
        r"\s*release:\s*(?P<release>\S+)\s*$",
        re.MULTILINE,
    )
    """The upgrade candidate, read from the repository half of an `info` block.

    `info` prints an `Installed package:` section before this one, opening on an
    identically shaped `Name :` line, so the pattern anchors on the repository
    heading and takes the line directly under it.
    """
    _SEARCH_REGEXP = re.compile(
        r"^(?P<package_id>\S+)\s+- (?P<description>.+)$",
        re.MULTILINE,
    )

    version_regexes = (r"eopkg(?:\.bin)?\s+(?P<version>\S+)",)
    """eopkg `5.0.0` names itself `eopkg.bin` in its banner, so the pattern makes
    that suffix optional. Without it nothing matches, no version is detected, and
    the manager silently leaves the pool on every Solus host running `5.x`.

    The name is fixed, not read from `argv[0]`: `/usr/bin/eopkg` and
    `/usr/bin/eopkg-cli` are both symlinks to `eopkg.bin`, and all three spellings
    print the same banner.

    ```{code-block} shell-session

    $ eopkg --version
    eopkg.bin 5.0.0
    ```

    ```{code-block} shell-session

    $ eopkg --version
    eopkg 4.4.0
    ```
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        ```{code-block} shell-session

        $ eopkg --no-color list-installed --install-info
        Package Name          |St|        Version|  Rel.|  Distro|             Date
        ===========================================================================
        aalib                 | i|        1.4.0_5|     9|   Solus|07 Sep 2026 10:08
        abseil-cpp            | i|     20260107.1|    11|   Solus|07 Sep 2026 10:08
        accounts-qml-module   | i|            0.7|     6|   Solus|07 Sep 2026 10:08
        accountsservice       | i|        23.13.9|    38|   Solus|07 Sep 2026 10:08
        acl                   | i|          2.3.2|    22|   Solus|07 Sep 2026 10:08
        alsa-firmware         | i|          1.2.4|     8|   Solus|07 Sep 2026 10:08
        alsa-lib              | i|         1.2.14|    41|   Solus|07 Sep 2026 10:08
        alsa-plugins          | i|         1.2.12|    26|   Solus|07 Sep 2026 10:08
        alsa-ucm-conf         | i|         1.2.13|     1|   Solus|07 Sep 2026 10:08
        alsa-utils            | i|         1.2.13|    29|   Solus|07 Sep 2026 10:08
        anthy                 | i|          9100h|     4|   Solus|07 Sep 2026 10:08
        aom                   | i|         3.12.1|    26|   Solus|07 Sep 2026 10:08
        appstream             | i|          1.1.2|    17|   Solus|07 Sep 2026 10:08
        appstream-catalog     | i|       20260417|    52|   Solus|07 Sep 2026 10:08
        appstream-qt6         | i|          1.1.2|    17|   Solus|07 Sep 2026 10:08
        argon2                | i|       20190702|     6|   Solus|07 Sep 2026 10:08
        ```

        The listing carries no footer: its last line is a package, so every line
        after the two header rows is one. A package whose name overflows the
        first column pushes the pipe right instead of being truncated, which is
        why the regex anchors on the pipes rather than on fixed offsets.
        """
        output = self.run_cli("list-installed", "--install-info")

        yield from self.parse_regex_lines(self._LIST_REGEXP, output)

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        Two queries, because one cannot answer both halves. `list-upgrades`
        names what is outdated but `--install-info` describes each package *as
        installed*, so its version column is the current one and the upgrade
        target appears nowhere. `info` holds the target, and it takes every
        package name at once, so the whole listing costs one extra invocation
        rather than one per package.

        Both sides are reported as `{version}-{release}`, the pair eopkg builds
        its package files from (`htop-3.5.3-30-1-x86_64.eopkg`). A bare version
        would hide the release, and a release-only rebuild is a real upgrade
        that would then read as the same version on both sides. This is the one
        operation where that matters, which is why `installed` above still
        reports the bare version: changing it would rewrite the version string
        every snapshot carries.

        ```{code-block} shell-session

        $ eopkg --no-color list-upgrades --install-info
        Package Name          |St|        Version|  Rel.|  Distro|             Date
        ===========================================================================
        acl                  | i|          2.3.2|    22|   Solus|07 Sep 2026 10:08
        alsa-lib             | i|         1.2.14|    41|   Solus|07 Sep 2026 10:08
        alsa-ucm-conf        | i|         1.2.13|     1|   Solus|07 Sep 2026 10:08
        alsa-utils           | i|         1.2.13|    29|   Solus|07 Sep 2026 10:08
        anthy                | i|          9100h|     4|   Solus|07 Sep 2026 10:08
        aom                  | i|         3.12.1|    26|   Solus|07 Sep 2026 10:08
        appstream            | i|          1.1.2|    17|   Solus|07 Sep 2026 10:08
        ```

        `info` prints an `Installed package:` section before the repository one
        whenever the package is installed, and both open on an identically
        shaped `Name :` line. That is why {attr}`_CANDIDATE_REGEXP` anchors on
        the repository heading rather than on the field name. The block below
        shows a package that is *not* installed, so only the repository half
        appears:

        ```{code-block} console

        $ eopkg --no-color info htop
        htop package is not installed
        Package found in Solus repository:
        Name                : htop, version: 3.5.3, release: 30
        Summary             : htop (interactive process viewer for Linux)
        Description         : htop is an interactive process viewer for Linux.
        Licenses            : GPL-2.0-or-later
        Component           : system.utils
        Dependencies        : ncurses glibc libcap2 lm_sensors
        Distribution        : Solus, Dist. Release: 1
        Architecture        : x86_64, Installed Size: 397.03 KB, Package Size: 159.05
                              KB
        Reverse Dependencies: htop-dbginfo
        ```
        """
        output = self.run_cli("list-upgrades", "--install-info")

        installed: dict[str, str] = {}
        for line in output.splitlines():
            match = self._UPGRADE_REGEXP.match(line)
            if match:
                installed[match.group("package_id")] = (
                    f"{match.group('version')}-{match.group('release')}"
                )
        if not installed:
            return

        candidates = {
            match.group("package_id"): (
                f"{match.group('version')}-{match.group('release')}"
            )
            for match in self._CANDIDATE_REGEXP.finditer(
                self.run_cli("info", *installed),
            )
        }

        for package_id, installed_version in installed.items():
            yield self.package(
                id=package_id,
                installed_version=installed_version,
                # A package pulled from the repository since the listing was
                # built has no candidate section, and is reported without one
                # rather than dropped: it is still outdated.
                latest_version=candidates.get(package_id),
            )

    @search_capabilities(exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        ```{caution}
        Search does not supports exact matching.
        ```

        Naked search without parameters is the same as extended search with all filtering
        parameters (i.e. `--name --summary --description`):

        ```{code-block} console

        $ eopkg --no-color search firefox
        gjs-dbginfo                 - Debug symbols for gjs
        bleachbit                   - BleachBit frees disk space and maintains privacy
        firefox                     - Firefox web browser
        eid-mw-firefox              - Belgian eID add-on for Mozilla Firefox
        gjs                         - GNOME JavaScript
        font-fira-ttf               - Mozilla's new typeface, used in Firefox OS
        geckodriver                 - WebDriver for Firefox
        firefox-dbginfo             - Debug symbols for firefox
        nvidia-vaapi-driver-dbginfo - Debug symbols for nvidia-vaapi-driver
        font-clear-sans-ttf         - Clear Sans Fonts - TrueType
        gjs-devel                   - Development files for gjs
        geckodriver-dbginfo         - Debug symbols for geckodriver

        $ eopkg --no-color search firefox --name --summary --description
        gjs-dbginfo                 - Debug symbols for gjs
        bleachbit                   - BleachBit frees disk space and maintains privacy
        firefox                     - Firefox web browser
        eid-mw-firefox              - Belgian eID add-on for Mozilla Firefox
        gjs                         - GNOME JavaScript
        font-fira-ttf               - Mozilla's new typeface, used in Firefox OS
        geckodriver                 - WebDriver for Firefox
        firefox-dbginfo             - Debug symbols for firefox
        nvidia-vaapi-driver-dbginfo - Debug symbols for nvidia-vaapi-driver
        font-clear-sans-ttf         - Clear Sans Fonts - TrueType
        gjs-devel                   - Development files for gjs
        geckodriver-dbginfo         - Debug symbols for geckodriver
        ```

        For default search on package name only, we rescript filtering to `--name` only:

        ```{code-block} shell-session

        $ eopkg --no-color search --name htop
        htop            - htop (interactive process viewer for Linux)
        htop-dbginfo    - Debug symbols for htop
        neohtop         - Blazing-fast system monitoring for your desktop.
        neohtop-dbginfo - Debug symbols for neohtop
        ```

        Summaries reach this listing exactly as the repository index stores them,
        character references included, where `list-available` resolves the same
        text. So `imagemagick` describes itself as `ImageMagick&#xAE; suite` here
        and `ImageMagick® suite` there, and {func}`html.unescape` reconciles the
        two. Measured against eopkg `4.4.0`.

        ```{code-block} shell-session

        $ eopkg --no-color search --name imagemagick
        imagemagick         - ImageMagick&#xAE; suite to create, edit, compose, or convert bitmap images
        imagemagick-dbginfo - Debug symbols for imagemagick
        imagemagick-devel   - Development files for imagemagick
        imagemagick-docs    - Documentation for imagemagick
        ```
        """
        # Extended search is the default behavior, so it adds no flag at all:
        # an empty string would be passed through as an empty argv element.
        # Non-extended search restricts matching to the package name.
        args = () if extended else ("--name",)

        output = self.run_cli("search", *args, query)

        for package_id, description in self._SEARCH_REGEXP.findall(output):
            yield self.package(id=package_id, description=unescape(description))

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        ```{code-block} shell-session

        $ sudo eopkg --no-color install --yes-all htop
        Total size of package(s): 159.05 KB
        Downloading 1 package resources (0 cached)
        Downloaded htop-3.5.3-30-1-x86_64.eopkg
        Finished downloading packages.
        Disabling keyboard interrupts for file operations.
        Installing 1 / 1
        Installing htop, version 3.5.3, release 30

        Extracting the files of htop (100%) [complete]
        Installed htop
        ```
        """
        return self.run_cli("install", "--yes-all", package_id, sudo=True)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all outdated packages.

        ```{code-block} shell-session

        $ sudo eopkg --no-color upgrade --yes-all
        ```
        """
        return self.build_cli("upgrade", "--yes-all", sudo=True)

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the provided package.

        ```{code-block} shell-session

        $ sudo eopkg --no-color upgrade --yes-all bash
        Updating repositories
        Updating repository: Solus
        Disabling keyboard interrupts for file operations.
        Downloaded eopkg-index.xml.xz.sha1sum

        Solus repository information is up-to-date.
        No packages to upgrade.
        ```
        """
        return self.build_cli("upgrade", "--yes-all", package_id, sudo=True)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        ```{code-block} shell-session

        $ sudo eopkg --no-color remove --yes-all htop
        The following list of packages will be removed
        in the respective order to satisfy dependencies:
        htop
        Disabling keyboard interrupts for file operations.
        Removing package htop
        Removed htop
        ```
        """
        return self.run_cli("remove", "--yes-all", package_id, sudo=True)

    def sync(self) -> None:
        """Sync package metadata.

        ```{code-block} shell-session

        $ sudo eopkg --no-color update-repo
        Updating repository: Solus
        Disabling keyboard interrupts for file operations.
        Downloaded eopkg-index.xml.xz.sha1sum

        Solus repository information is up-to-date.
        ```
        """
        self.run_cli("update-repo", sudo=True)

    def cleanup_cache(self) -> None:
        """Removes things we don't need anymore:
        - orphaned packages,
        - outdated package locks
        - package cache and package manager cache

        ```{code-block} shell-session

        $ sudo eopkg --no-color remove-orphans --yes-all
        The following list of packages will be removed
        in the respective order to satisfy dependencies:
        flashrom libboost celt
        Disabling keyboard interrupts for file operations.
        Removing package flashrom
        Removed flashrom
        Removing package libboost
        Removed libboost
        Removing package celt
        Removed celt
        ```

        `clean` releases stale transaction locks and prints nothing when none
        are held, which is its usual outcome.

        ```{code-block} shell-session

        $ sudo eopkg --no-color clean
        ```

        ```{code-block} shell-session

        $ sudo eopkg --no-color delete-cache
        Cleaning package cache /var/cache/eopkg/packages...
        Cleaning source archive cache /var/cache/eopkg/archives...
        Cleaning temporary directory /var/eopkg...
        Removing cache file /var/cache/eopkg/groupdb.cache...
        Removing cache file /var/cache/eopkg/installdb.cache...
        Removing cache file /var/cache/eopkg/packagedb.cache...
        ```
        """
        self.run_cli("remove-orphans", "--yes-all", sudo=True)
        self.run_cli("clean", sudo=True)
        self.run_cli("delete-cache", sudo=True)
