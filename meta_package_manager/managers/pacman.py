# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
# All Rights Reserved.
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
from typing import Iterator

from click_extra.platform import LINUX

from ..base import Package, PackageManager
from ..capabilities import search_capabilities, version_not_implemented


class Pacman(PackageManager):
    """See command equivalences at: https://wiki.archlinux.org/title/Pacman/Rosetta."""

    homepage_url = "https://wiki.archlinux.org/title/pacman"

    platforms = frozenset({LINUX})

    requirement = "5.0.0"

    pre_args = ("--noconfirm",)

    version_regex = r".*Pacman\s+v(?P<version>\S+)"
    r"""Search version right after the ``Pacman `` string.

    .. code-block:: shell-session

        ► pacman --version

         .--.                  Pacman v6.0.1 - libalpm v13.0.1
        / _.-' .-.  .-.  .-.   Copyright (C) 2006-2021 Pacman Development Team
        \  '-. '-'  '-'  '-'   Copyright (C) 2002-2006 Judd Vinet
         '--'
                            This program may be freely redistributed under
                            the terms of the GNU General Public License.
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            ► pacman --noconfirm --query
            a52dec 0.7.4-11
            aalib 1.4rc5-14
            abseil-cpp 20211102.0-2
            accountsservice 22.08.8-2
            acl 2.3.1-2
            acme.sh 3.0.2-1
            acpi 1.7-3
            acpid 2.0.33-1
        """
        output = self.run_cli("--query")

        regexp = re.compile(r"(\S+) (\S+)")
        for package in output.splitlines():
            match = regexp.match(package)
            if match:
                package_id, installed_version = match.groups()
                yield self.package(id=package_id, installed_version=installed_version)

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            ► pacman --noconfirm --query --upgrades
            linux 4.19.1.arch1-1 -> 4.19.2.arch1-1
            linux-headers 4.19.1.arch1-1 -> 4.19.2.arch1-1
        """
        output = self.run_cli("--query", "--upgrades")

        regexp = re.compile(r"(\S+) (\S+) -> (\S+)")
        for package in output.splitlines():
            match = regexp.match(package)
            if match:
                package_id, installed_version, latest_version = match.groups()
                yield self.package(
                    id=package_id,
                    latest_version=latest_version,
                    installed_version=installed_version,
                )

    @search_capabilities(extended_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. caution::
            Search does not supports extended matching.

        .. code-block:: shell-session

            ► pacman --noconfirm --sync --search fire
            extra/dump_syms 0.0.7-1
                Symbol dumper for Firefox
            extra/firefox 99.0-1
                Standalone web browser from mozilla.org
            extra/firefox-i18n-ach 99.0-1
                Acholi language pack for Firefox
            extra/firefox-i18n-af 99.0-1
                Afrikaans language pack for Firefox
            extra/firefox-i18n-an 99.0-1
                Aragonese language pack for Firefox
            extra/firefox-i18n-ar 99.0-1
                Arabic language pack for Firefox
            extra/firefox-i18n-ast 99.0-1
                Asturian language pack for Firefox
        """
        if exact:
            query = f"^{query}$"

        output = self.run_cli("--sync", "--search", query)

        regexp = re.compile(
            r"(?P<repo_id>\S+?)/(?P<package_id>\S+)\s+(?P<version>\S+).*\n\s+(?P<description>.+)",
            re.MULTILINE | re.VERBOSE,
        )

        for repo_id, package_id, version, description in regexp.findall(output):
            yield self.package(
                id=package_id,
                description=description,
                latest_version=version,
            )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            ► sudo pacman --noconfirm --sync firefox
        """
        return self.run_cli("--sync", package_id, sudo=True)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade the package provided as parameter.

        .. code-block:: shell-session

            ► sudo pacman --noconfirm --sync --refresh --sysupgrade
        """
        return self.build_cli("--sync", "--refresh", "--sysupgrade", sudo=True)

    @version_not_implemented
    def upgrade_one_cli(
        self, package_id: str, version: str | None = None
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the package provided as parameter.

        .. code-block:: shell-session

            ► sudo pacman --noconfirm --sync firefox
        """
        return self.build_cli("--sync", package_id, sudo=True)

    def remove(self, package_id: str) -> str:
        """Removes a package.

        .. code-block:: shell-session

            ► sudo pacman --noconfirm --remove firefox
        """
        return self.run_cli("--remove", package_id, sudo=True)

    def sync(self) -> None:
        """Sync package metadata.

        .. code-block:: shell-session

            ► pacman --noconfirm --sync --refresh
        """
        self.run_cli("--sync", "--refresh")

    def cleanup(self) -> None:
        """Removes things we don't need anymore.

        .. code-block:: shell-session

            ► sudo pacman --noconfirm --sync --clean --clean
        """
        self.run_cli("--sync", "--clean", "--clean", sudo=True)


class Pacaur(Pacman):
    """``Pacaur`` wraps ``pacman`` and shadows its options."""

    homepage_url = "https://github.com/E5ten/pacaur"

    requirement = "4.0.0"

    version_regex = r"pacaur\s+(?P<version>\S+)"
    r"""Search version right after the ``pacaur`` string.

    .. code-block:: shell-session

        ► pacaur --version
        pacaur 4.8.6
    """


class Paru(Pacman):
    """``paru`` wraps ``pacman`` and shadows its options."""

    homepage_url = "https://github.com/Morganamilo/paru"

    # v1.9.3 is the first version implementing the --sysupgrade option.
    requirement = "1.9.3"

    version_regex = r"paru\s+v(?P<version>\S+)"
    r"""Search version right after the ``paru`` string.

    .. code-block:: shell-session

        ► paru --version
        paru v1.10.0 - libalpm v13.0.1
    """


class Yay(Pacman):
    """``yay`` wraps ``pacman`` and shadows its options."""

    homepage_url = "https://github.com/Jguer/yay"

    requirement = "11.0.0"

    version_regex = r"yay\s+v(?P<version>\S+)"
    r"""Search version right after the ``yay`` string.

    .. code-block:: shell-session

        ► yay --version
        yay v11.1.2 - libalpm v13.0.1
    """
