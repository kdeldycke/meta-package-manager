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

from extra_platforms import ALL_PLATFORMS

from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


RELEASE_STATES = ("snapshot", "devel", "alpha", "beta", "stable")
"""The quality states a PEAR release can carry.

Source: `PEAR_Validate::getValidStates()` in `PEAR/Validate.php`, repeated
verbatim in `PEAR/Common.php` and both REST clients.

The listing parsers key on this vocabulary because it is what separates a
package row from the table furniture around it: a row ends on one of these
lowercase words, while the `PACKAGE VERSION STATE` header ends on an uppercase
one and the `(no packages installed)` placeholder on a parenthesis.
"""

_STATES = "|".join(RELEASE_STATES)


class PEAR(PackageManager):
    """The PHP Extension and Application Repository.

    PEAR ships with PHP itself and installs libraries into the interpreter's
    `php_dir`, against its own registry at `pear.php.net`.

    ```{important}
    Whether that needs root is a property of the PHP install, not of PEAR: a
    distribution's `php_dir` is `/usr/share/php` and refuses an ordinary user
    with `Cannot install, php_dir for channel "pear.php.net" is not writable
    by the current user`. So the mutating operations carry privileged markers
    but leave them dormant, exactly as the other language managers do: `mpm
    --sudo`, or a `[mpm.managers.pear] sudo = true` entry, escalates them.

    The better fix is to own the prefix instead. PEAR is fully relocatable, and
    every role directory has to move together: repointing `php_dir` alone fails
    late, on `failed to mkdir /usr/share/php/tests/...`, because `test_dir` is
    a separate setting. With `php_dir`, `bin_dir`, `data_dir`, `test_dir`,
    `doc_dir`, `cfg_dir`, `www_dir`, `man_dir`, `temp_dir`, `download_dir` and
    `cache_dir` all under one writable prefix, an install needs no privilege at
    all.
    ```

    ```{caution}
    Every network operation costs one REST round-trip per package, and
    `pear.php.net` answers slowly: `outdated` measured 63 seconds warm and 105
    seconds cold against a host carrying only six packages, so it approaches
    mpm's 120-second read-only cap on an inventory barely larger. Raise
    `mpm --timeout` on a host with more. `installed` is unaffected, reading the
    local registry with no network at all.
    ```

    ```{note}
    `search` is not implemented. `pear search` resolves through the same
    per-package REST walk (`PEAR_REST_10::listAll()` with its `$basic`
    parameter false, one `p/<name>/info.xml` fetch apiece), and no run of it
    here ever returned: two attempts were abandoned after 15 and 30 minutes,
    the second having reached "50%". `remote-list` is no way around it either,
    costing 524 seconds on a cold cache. Both are far past the read-only cap,
    so mpm skips the operation and `install` falls through to installing the
    named package directly.
    ```

    ```{note}
    A package is reported under its bare name, the spelling `pear install`
    takes. PEAR identities are really channel-qualified (`[channel/]package`),
    so two channels shipping the same name would collapse onto one entry; in
    practice `pear.php.net` is the only populated one.
    ```

    Documentation: [PEAR manual](https://pear.php.net/manual/en/guide.users.commandline.cli.php).
    """

    name = "PEAR"

    homepage_url = "https://pear.php.net"
    logo = "php"

    platforms = ALL_PLATFORMS

    requirement = ">=1.10.0"
    """The series every current distribution ships, and the one upstream still
    releases from (`1.10.18`, 2026-01-25).

    A conservative floor rather than a feature bisect: every verb driven here is
    older, the bare `upgrade` delegation to `doUpgradeAll` being present already
    in `1.9.5`.
    """

    _INSTALLED_REGEXP = re.compile(
        rf"^(?P<package_id>\S+)\s+(?P<installed_version>\S+)\s+(?:{_STATES})\s*$",
    )
    _OUTDATED_REGEXP = re.compile(
        rf"^\S+\s+(?P<package_id>\S+)"
        rf"\s+(?P<installed_version>\S+)\s+\((?:{_STATES})\)"
        rf"\s+(?P<latest_version>\S+)\s+\((?:{_STATES})\)"
        rf"\s+\S+\s*$",
    )

    version_cli_options = ("version",)
    """`pear --version` is not a thing: it is rejected as `Command '--version'
    is not valid`, and the version comes from the `version` verb instead.
    """

    version_regexes = (r"PEAR Version:\s+(?P<version>\S+)",)
    """
    ```{code-block} shell-session

    $ pear version
    PEAR Version: 1.10.16
    PHP Version: 8.4.24
    Zend Engine Version: 4.4.24
    Running on: Linux debian 6.12.94+deb13-arm64 #1 SMP Debian 6.12.94-1 (2026-06-20) aarch64
    ```
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        `--allchannels` is not optional: a bare `pear list` reports the default
        channel alone and silently omits everything installed from any other.
        The listing is a section per channel, and the parser keeps only the rows
        closing on a release state.

        ```{code-block} shell-session

        $ pear list --allchannels
        INSTALLED PACKAGES, CHANNEL __URI:
        ==================================
        (no packages installed)

        INSTALLED PACKAGES, CHANNEL DOC.PHP.NET:
        ========================================
        (no packages installed)

        INSTALLED PACKAGES, CHANNEL PEAR.PHP.NET:
        =========================================
        PACKAGE          VERSION STATE
        Archive_Tar      1.5.0   stable
        Console_Getopt   1.4.3   stable
        PEAR             1.10.16 stable
        PEAR_Manpages    1.10.0  stable
        Structures_Graph 1.2.0   stable
        XML_Util         1.4.5   stable

        INSTALLED PACKAGES, CHANNEL PECL.PHP.NET:
        =========================================
        (no packages installed)
        ```
        """
        output = self.run_cli("list", "--allchannels")
        yield from self.parse_regex_lines(self._INSTALLED_REGEXP, output)

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        `list-upgrades` walks every registered channel on its own, so it takes
        no `--allchannels`. Each version column carries its release state in
        parentheses, which is what tells a package row from the header above it.

        ```{code-block} shell-session

        $ pear list-upgrades
        PEAR.PHP.NET AVAILABLE UPGRADES (STABLE):
        =========================================
        CHANNEL      PACKAGE     LOCAL            REMOTE           SIZE
        pear.php.net Archive_Tar 1.5.0 (stable)   1.6.0 (stable)   22kB
        pear.php.net PEAR        1.10.16 (stable) 1.10.18 (stable) 288kB
        ```
        """
        output = self.run_cli("list-upgrades")
        yield from self.parse_regex_lines(self._OUTDATED_REGEXP, output)

    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        A version is appended to the name with a dash, the `Package-1.1` form
        PEAR's own `install` help documents. PEAR package names use underscores,
        so the dash never collides with one.

        ```{code-block} shell-session

        $ pear install Text_Password
        downloading Text_Password-1.2.1.tgz ...
        Starting to download Text_Password-1.2.1.tgz (5,631 bytes)
        .....done: 5,631 bytes
        install ok: channel://pear.php.net/Text_Password-1.2.1
        ```

        ```{code-block} shell-session

        $ pear install Text_Password-1.2.1
        Starting to download Text_Password-1.2.1.tgz (5,631 bytes)
        .....done: 5,631 bytes
        install ok: channel://pear.php.net/Text_Password-1.2.1
        ```
        """
        # Marked privileged so --sudo / `[mpm.managers.pear] sudo = true` can
        # escalate a system-PHP install; dormant by default.
        return self.run_cli(
            "install",
            f"{package_id}-{version}" if version else package_id,
            sudo=True,
        )

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all outdated packages.

        `upgrade` with no package named is the documented spelling: the separate
        `upgrade-all` verb still exists but announces itself as deprecated in
        favour of this one, and both land on the same `doUpgradeAll` handler.

        ```{caution}
        PEAR is itself a PEAR package, so an upgrade of everything replaces the
        tool along with the libraries it manages.
        ```

        ```{code-block} shell-session

        $ pear upgrade
        ```
        """
        return self.build_cli("upgrade", sudo=True)

    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the provided package.

        ```{code-block} shell-session

        $ pear upgrade Text_Password
        ```
        """
        return self.build_cli(
            "upgrade",
            f"{package_id}-{version}" if version else package_id,
            sudo=True,
        )

    def remove(self, package_id: str) -> str:
        """Remove one package.

        ```{code-block} shell-session

        $ pear uninstall Text_Password
        uninstall ok: channel://pear.php.net/Text_Password-1.2.1
        ```
        """
        return self.run_cli("uninstall", package_id, sudo=True)

    def sync(self) -> None:
        """Sync package metadata.

        Refreshes the definition of every registered channel. A channel whose
        server answers badly is reported and stepped over, the run still
        exiting `0`.

        ```{code-block} shell-session

        $ pear update-channels
        Updating channel "doc.php.net"
        Error: Unable to create XML parser
        Invalid channel.xml file
        Updating channel "pear.php.net"
        Channel "pear.php.net" is up to date
        Updating channel "pecl.php.net"
        Update of Channel "pecl.php.net" succeeded
        ```
        """
        self.run_cli("update-channels", sudo=True)

    def cleanup_cache(self) -> None:
        """Clear the cached REST responses.

        ```{code-block} shell-session

        $ pear clear-cache
        reading directory /tmp/pear/cache
        100 cache entries cleared
        ```
        """
        self.run_cli("clear-cache", sudo=True)
