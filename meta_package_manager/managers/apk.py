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

from extra_platforms import LINUX_LIKE

from ..base import PackageManager
from ..capabilities import search_capabilities, version_not_implemented

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..base import Package


class APK(PackageManager):
    """Alpine Package Keeper (``apk``) used by Alpine Linux.

    Documentation: https://wiki.alpinelinux.org/wiki/Alpine_Package_Keeper
    """

    homepage_url = "https://gitlab.alpinelinux.org/alpine/apk-tools"

    platforms = LINUX_LIKE

    requirement = ">=2.10.0"
    """The ``list`` applet, used by :py:meth:`installed` and :py:meth:`outdated`,
    was introduced in version ``2.10.0``.
    """

    pre_args = ("--no-progress",)
    """Suppress progress indicators so log lines are stable when parsing.

    Source: ``apk(8)`` global options.
    """

    _NAME_VERSION_REGEXP = re.compile(r"^(?P<package_id>.+)-(?P<version>\d\S*)$")
    """Split an apk pkgver string into package name and version.

    Alpine convention: ``<name>-<version>-r<release>``. The version starts at
    the last hyphen followed by a digit, so trailing ``-r<n>`` release suffixes
    stay with the version while leading ``-<digit>`` segments in the name (like
    ``python3``) stay with the name.
    """

    _INSTALLED_REGEXP = re.compile(
        r"^(?P<pkgver>\S+)\s.+\[installed\]\s*$",
        re.MULTILINE,
    )
    """Match installed entries from ``apk list --installed`` output.

    Each line has the format
    ``<pkgver> <arch> {<origin>} (<license>) [installed]``.
    """

    _OUTDATED_REGEXP = re.compile(
        r"^(?P<pkgver>\S+)\s.+\[upgradable from:\s+(?P<from_pkgver>\S+)\]\s*$",
        re.MULTILINE,
    )
    """Match upgradable entries from ``apk list --upgradable`` output.

    Each line has the format
    ``<pkgver> <arch> {<origin>} (<license>) [upgradable from: <pkgver>]``.
    """

    version_regexes = (r"apk-tools\s+(?P<version>[^\s,]+)",)
    """
    .. code-block:: shell-session

        $ apk --version
        apk-tools 2.14.10, compiled for x86_64.
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            $ apk --no-progress list --installed
            acl-2.2.53-r0 x86_64 {acl} (LGPL-2.1-or-later AND GPL-2.0-or-later) [installed]
            alpine-baselayout-3.4.3-r1 x86_64 {alpine-baselayout} (GPL-2.0-only) [installed]
            apk-tools-2.14.0-r5 x86_64 {apk-tools} (GPL-2.0-only) [installed]
            busybox-1.36.1-r5 x86_64 {busybox} (GPL-2.0-only) [installed]
            python3-3.11.6-r0 x86_64 {python3} (PSF-2.0) [installed]
        """
        output = self.run_cli("list", "--installed")

        for match in self._INSTALLED_REGEXP.finditer(output):
            name_match = self._NAME_VERSION_REGEXP.match(match.group("pkgver"))
            if name_match:
                yield self.package(
                    id=name_match.group("package_id"),
                    installed_version=name_match.group("version"),
                )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. caution::
            Reads from the local repository cache. Run :py:meth:`sync` first
            to refresh the index.

        .. code-block:: shell-session

            $ apk --no-progress list --upgradable
            acl-2.3.1-r0 x86_64 {acl} (LGPL-2.1-or-later) [upgradable from: acl-2.2.53-r0]
            python3-3.11.7-r0 x86_64 {python3} (PSF-2.0) [upgradable from: python3-3.11.6-r0]
        """
        output = self.run_cli("list", "--upgradable")

        for match in self._OUTDATED_REGEXP.finditer(output):
            new_match = self._NAME_VERSION_REGEXP.match(match.group("pkgver"))
            old_match = self._NAME_VERSION_REGEXP.match(match.group("from_pkgver"))
            if new_match and old_match:
                yield self.package(
                    id=new_match.group("package_id"),
                    installed_version=old_match.group("version"),
                    latest_version=new_match.group("version"),
                )

    @search_capabilities(exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. caution::
            ``apk search`` matches package names with case-insensitive
            substring globbing. Exact matching is not supported and is
            handled by
            :py:meth:`meta_package_manager.base.PackageManager.refiltered_search`.
            Extended search adds the ``--description`` flag so the query is
            also matched against package descriptions.

        .. code-block:: shell-session

            $ apk --no-progress search --verbose firefox
            firefox-120.0-r0
            firefox-esr-115.5.0-r0
            firefox-langpack-de-120.0-r0

        .. code-block:: shell-session

            $ apk --no-progress search --verbose --description ntp
            chrony-4.4-r1
            ntp-4.2.8_p17-r0
            openntpd-6.8_p1-r1
        """
        args = ["search", "--verbose"]
        if extended:
            args.append("--description")
        args.append(query)
        output = self.run_cli(*args)

        for line in output.splitlines():
            match = self._NAME_VERSION_REGEXP.match(line.strip())
            if match:
                yield self.package(
                    id=match.group("package_id"),
                    latest_version=match.group("version"),
                )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            $ sudo apk --no-progress add firefox
        """
        return self.run_cli("add", package_id, sudo=True)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        .. code-block:: shell-session

            $ sudo apk --no-progress upgrade
        """
        return self.build_cli("upgrade", sudo=True)

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade one package.

        .. code-block:: shell-session

            $ sudo apk --no-progress upgrade firefox
        """
        return self.build_cli("upgrade", package_id, sudo=True)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        .. code-block:: shell-session

            $ sudo apk --no-progress del firefox
        """
        return self.run_cli("del", package_id, sudo=True)

    def sync(self) -> None:
        """Synchronize the local package index from remote repositories.

        .. code-block:: shell-session

            $ sudo apk --no-progress update
        """
        self.run_cli("update", sudo=True)

    def cleanup(self) -> None:
        """Drop the local package cache.

        .. code-block:: shell-session

            $ sudo apk --no-progress cache clean
        """
        self.run_cli("cache", "clean", sudo=True)
