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

from extra_platforms import CRUX

from ..capabilities import search_capabilities, version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class PrtGet(PackageManager):
    """The ports front-end of CRUX.

    Documentation: [`prt-get(8)` man page](https://crux.nu/Main/Prt-get).

    ```{caution}
    CRUX builds every port from source, so an install or an upgrade compiles.
    `mpm` caps a mutating operation at 500 seconds, which a large port outlasts
    by hours. Raise it for this manager with `[mpm.overrides.prt-get] timeout`.
    ```

    ```{note}
    {meth}`sync` runs the sibling `ports` binary rather than `prt-get`, that
    being the tool CRUX gives the ports tree. `mpm` resolves it from the same
    directory as {attr}`cli_path
    <meta_package_manager.execution.CLIExecutor.cli_path>`.
    ```

    ```{warning}
    `prt-get listorphans` is deliberately left unmapped. It lists "ports with
    no packages depending on them", which on a stock CRUX install includes
    `bash`, `binutils` and `coreutils`: the base system is depended on by
    nothing, so feeding that list to an orphan sweep would remove the machine.
    That is a different question from the one {meth}`~PackageManager.orphans`
    asks, which is which packages were pulled in as dependencies and are no
    longer required.
    ```
    """

    id = "prt-get"
    """The CLI name, which the `PrtGet` class name cannot spell: a hyphen is not
    valid in a Python identifier.
    """

    name = "CRUX prt-get"

    homepage_url = "https://crux.nu/Main/Prt-get"

    keywords = ("crux",)

    platforms = CRUX

    default_sudo = True

    requirement = ">=5.19"
    """The `5.19` series is what every supported CRUX ships: `5.19.6` on CRUX
    `3.7` and `5.19.9` on CRUX `3.8`.

    This is not a bisected minimum. Every operation below is far older than
    that: upstream's own `ChangeLog` dates `printf` to `0.3.4`, `listinst` to
    `0.3.1pre1`, `dsearch` to `0.2.9` and `sysup` to `0.4.0alpha2`, all of them
    predating the newest entry that file carries (`5.16`, 2008). So the floor
    records the series this wrapper was driven against rather than claiming
    compatibility with releases nobody runs.
    """

    cli_names = ("prt-get",)

    version_cli_options = ("version",)
    """`prt-get` answers `--version` with `prt-get: Unknown option: --version`.
    The version is a subcommand instead.
    """

    version_regexes = (r"prt-get\s+(?P<version>\S+)",)
    """
    ```{code-block} shell-session

    $ prt-get version
    prt-get 5.19.5 by Johannes Winkelmann, jw@tks6.net
    ```
    """

    _INSTALLED_REGEXP = re.compile(
        r"^(?P<package_id>\S+)\s+(?P<installed_version>\S+)\s*$",
        re.MULTILINE,
    )
    """Match the `name version-release` rows of `prt-get listinst -v`."""

    _OUTDATED_REGEXP = re.compile(
        r"^(?P<package_id>\S+)\s+"
        r"(?P<installed_version>\S+)\s+"
        r"(?P<latest_version>\S+)\s*$",
        re.MULTILINE,
    )
    """Match the rows of the `prt-get diff` table, skipping its two-line header.

    Neither header line survives the anchors: `Port Installed Available in the
    ports tree` carries four more tokens past the third group, and the
    `Differences between installed packages and ports tree:` title carries
    five, so `\\s*$` fails on both. Data rows are padded to fixed-width
    columns, hence the trailing `\\s*`.
    """

    _SEARCH_REGEXP = re.compile(
        r"^(?P<package_id>[^|]+)\|"
        r"(?P<latest_version>[^|]*)\|"
        r"(?P<description>.*)$",
        re.MULTILINE,
    )
    """Match the `name|version|description` rows of the `printf` projection."""

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        The `[Config error: can't access /usr/ports/<collection>]` lines a host
        with an unsynced ports tree emits go to `stderr`, so they never reach
        this parser.

        ```{code-block} shell-session

        $ prt-get listinst -v
        acl 2.3.2-1
        attr 2.5.2-1
        autoconf 2.72-1
        automake 1.17-1
        bash 5.2.37-1
        bc 1.08.1-1
        ```
        """
        # `-v` has no long form: prt-get documents it as a bare general option.
        output = self.run_cli("listinst", "-v")

        for match in self._INSTALLED_REGEXP.finditer(output):
            yield self.package(
                id=match.group("package_id"),
                installed_version=match.group("installed_version"),
            )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        ```{caution}
        Compares the installed packages against the local ports tree, so it
        reports what the last {meth}`sync` fetched and not what CRUX publishes
        right now.
        ```

        ```{code-block} shell-session

        $ prt-get diff
        Differences between installed packages and ports tree:

        Port                Installed           Available in the ports tree

        acl                 2.3.2-1             2.4.0-1
        attr                2.5.2-1             2.6.0-1
        autoconf            2.72-1              2.73-1
        automake            1.17-1              1.18.1-1
        bash                5.2.37-1            5.3.15-1
        ```
        """
        output = self.run_cli("diff")

        for match in self._OUTDATED_REGEXP.finditer(output):
            yield self.package(
                id=match.group("package_id"),
                installed_version=match.group("installed_version"),
                latest_version=match.group("latest_version"),
            )

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        Lists the whole ports tree and lets
        {meth}`meta_package_manager.manager.PackageManager.refiltered_search`
        narrow it. `prt-get` does own two search commands, but neither reports
        a version: `search` and `dsearch` both print bare port names, and only
        the `printf` projection carries the version and the description. The
        tree is local and small, so dumping it costs less than enriching each
        hit: 789 ports rendered in 34 ms on the host this was driven on.

        The format string holds no space, so the command `mpm` discloses at
        `--verbosity INFO` can be pasted back into a shell unquoted.

        ```{code-block} shell-session

        $ prt-get printf %n|%v|%d\\n
        a2ps|4.15.8|ASCII to Postscript converter (Prettyprint)
        abseil-cpp|20260817.0|Abseil Common Libraries (C++)
        acl|2.4.0|Access Control Lists library
        adwaita-icon-theme|50.0|Adwaita Icon Theme
        alsa-lib|1.2.16.1|ALSA libraries
        alsa-oss|1.1.8|ALSA OSS Emulation
        ```
        """
        output = self.run_cli("printf", r"%n|%v|%d\n")

        for match in self._SEARCH_REGEXP.finditer(output):
            yield self.package(
                id=match.group("package_id"),
                description=match.group("description").strip(),
                latest_version=match.group("latest_version"),
            )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package, and the ports it depends on.

        `depinst` rather than `install`: the latter builds the named port
        alone and fails on the first missing dependency.

        ```{code-block} shell-session

        $ sudo prt-get depinst dosfstools
        =======> Building '/usr/ports/opt/dosfstools/dosfstools#4.2-1.pkg.tar.gz' succeeded.
        prt-get: installing dosfstools 4.2-1

        -- Packages installed
        dosfstools

        prt-get: installed successfully
        ```
        """
        return self.run_cli("depinst", package_id, sudo=True)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        ```{code-block} shell-session

        $ sudo prt-get sysup
        ```
        """
        return self.build_cli("sysup", sudo=True)

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade one package.

        ```{code-block} shell-session

        $ sudo prt-get update dosfstools
        ```
        """
        return self.build_cli("update", package_id, sudo=True)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        ```{code-block} shell-session

        $ sudo prt-get remove dosfstools

        -- Packages removed
        dosfstools
        ```
        """
        return self.run_cli("remove", package_id, sudo=True)

    def sync(self) -> None:
        """Sync the ports tree.

        ```{code-block} shell-session

        $ sudo ports -u
        Updating file list from crux.nu::ports/crux-3.8/xorg/
        Updating collection xorg
        Finished successfully
        ```
        """
        self.run_cli(
            "-u",
            override_cli_path=self.sibling_cli("ports", same_dir=True),
            sudo=True,
        )
