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

from click_extra.platform import WINDOWS

from ..base import Package, PackageManager
from ..capabilities import search_capabilities, version_not_implemented


class Scoop(PackageManager):

    name = "Scoop"

    homepage_url = "https://scoop.sh"

    platforms = frozenset({WINDOWS})

    requirement = "0.2.4"

    version_regex = r".*Scoop version:\s+v(?P<version>\S+)"
    """Search version right after the ``Scoop version:\n`` string.

    .. code-block:: shell-session

        ► scoop --version
        Current Scoop version:
        v0.2.4 - Released at 2022-08-08

        'main' bucket:
        5a5b13b6c (HEAD -> master, origin/master, origin/HEAD) oh-my-posh: Update to version 11.1.1
    """

    @staticmethod
    def remove_headers(text: str) -> str:
        results = text.split("---\n", 1)
        if len(results) != 2:
            return ""
        return results[1]

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            ►  scoop list
            Installed apps:

            Name   Version          Source Updated             Info
            ----   -------          ------ -------             ----
            7zip   22.01            main   2022-09-27 08:03:30
            dark   3.11.2           main   2022-09-27 08:04:26
            git    2.37.3.windows.1 main   2022-09-27 08:03:58
            python 3.10.7           main   2022-09-27 08:04:53
        """
        output = self.run_cli("list")

        regexp = re.compile(
            r"""
            (?P<package_id>\S+)  # Any string.
            \s+                  # Any number of blank chars.
            (?P<version>\S+)     # Version string.
            \s+                  # Any number of blank chars.
            .+                   # Any string.
            """,
            re.VERBOSE,
        )

        for package_id, version in regexp.findall(self.remove_headers(output)):
            yield self.package(id=package_id, installed_version=version)

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            ► scoop status
            Name           Installed Version Latest Version Missing Dependencies Info
            ----           ----------------- -------------- -------------------- ----
            demulshooter   16.7.2            18.7.3
            eduke32        20220611-10112    20220709-10115
            Teracopy-np                                                          Installed failed
            yuzu-pineapple EA-2804           EA-2830
        """
        output = self.run_cli("scoop", "status")

        regexp = re.compile(
            r"""
            (?P<package_id>\S+)         # Any string.
            \ +                         # One space or more.
            (?P<installed_version>\S*)  # Version string.
            \ +                         # One space or more.
            (?P<latest_version>\S*)     # Version string.
            """,
            re.VERBOSE,
        )

        for package_id, installed_version, latest_version in regexp.findall(
            self.remove_headers(output)
        ):
            yield self.package(
                id=package_id,
                latest_version=latest_version,
                installed_version=installed_version,
            )

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. caution::
            Search does not support extended or exact matching. So we returns the best subset of results and let
            :py:meth:`meta_package_manager.base.PackageManager.refiltered_search` refine them.

        .. code-block:: shell-session

            ► scoop search zip
            Results from local buckets...

            Name             Version         Source Binaries
            ----             -------         ------ --------
            7zip             22.01           main
            7zip19.00-helper 19.00           main
            busybox          4716-g31467ddfc main   bunzip2 | bzip2 | gunzip | gzip | unzip
            bzip2            1.0.8.0         main
            gow              0.8.0           main   bunzip2.exe | bzip2.exe | gzip.exe | zip.exe
            gzip             1.3.12          main
            lzip             1.20            main
            unzip            6.00            main
            zip              3.0             main
        """
        output = self.run_cli("search", query)

        regexp = re.compile(
            r"""
            (?P<package_id>\S+)  # Any string.
            \ +                  # One space or more.
            (?P<version>\S+)     # Version string.
            \ +                  # One space or more.
            \S+                  # Any string.
            """,
            re.VERBOSE,
        )

        for package_id, version in regexp.findall(self.remove_headers(output)):
            yield self.package(id=package_id, latest_version=version)

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            ► scoop install 7zip
            Installing '7zip' (22.01) [64bit] from main bucket
            7z2201-x64.msi (1.8 MB) [====================] 100%
            Checking hash of 7z2201-x64.msi ... ok.
            Extracting 7z2201-x64.msi ... done.
            Linking ~\\scoop\apps\7zip\\current => ~\\scoop\apps\7zip\22.01
            Creating shim for '7z'.
            Creating shortcut for 7-Zip (7zFM.exe)
            Persisting Codecs
            Persisting Formats
            Running post_install script...
            '7zip' (22.01) was installed successfully!
            Notes
            -----
            Add 7-Zip as a context menu by running: "C:\\scoop\apps\7zip\\current\\install-context.reg"
        """
        return self.run_cli("install", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: shell-session

            ► scoop update --all
        """
        return self.build_cli("update", "--all")

    @version_not_implemented
    def upgrade_one_cli(
        self, package_id: str, version: str | None = None
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: shell-session

            ► scoop update 7zip
        """
        return self.build_cli("update", package_id)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        .. code-block:: shell-session

            ► scoop uninstall 7zip --purge
            Uninstalling '7zip' (22.01).
            Removing shim '7z.shim'.
            Removing shim '7z.exe'.
            Removing shortcut ~\\AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs\\Scoop Apps\7-Zip.lnk
            Unlinking ~\\scoop\apps\7zip\\current
            '7zip' was uninstalled.
        """
        return self.run_cli("uninstall", package_id, "--purge")

    def sync(self) -> None:
        """Sync package metadata.

        .. code-block:: shell-session

            ► scoop status
            WARN  Scoop out of date. Run 'scoop update' to get the latest changes.

        .. code-block:: shell-session

            ► scoop update
            Updating Scoop...
            Updating 'main' bucket...
            Converting 'main' bucket to git repo...
            Checking repo... OK
            The main bucket was added successfully.
            Scoop was updated successfully!

        .. code-block:: shell-session

            ► scoop status
            Scoop is up to date.
            Everything is ok!
        """
        self.run_cli("update")

    def cleanup(self) -> None:
        """Removes things we don't need anymore.

        .. code-block:: shell-session

            ► scoop cleanup --all --cache
            Everything is shiny now!
        """
        self.run_cli("cleanup", "--all", "--cache")
