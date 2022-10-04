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
from ..capabilities import version_not_implemented


class Emerge(PackageManager):
    """

    Documentation:
    - https://wiki.gentoo.org/wiki/Portage#emerge
    - https://dev.gentoo.org/~zmedico/portage/doc/man/emerge.1.html

    See other command equivalences at: https://wiki.archlinux.org/title/Pacman/Rosetta
    """

    homepage_url = "https://wiki.gentoo.org/wiki/Portage#emerge"

    platforms = frozenset({LINUX})

    requirement = "3.0.0"

    version_regex = r"Portage\s+(?P<version>\S+)"
    """
    .. code-block:: shell-session

        ► emerge --version
        Portage 3.0.30 (python 3.9.9-final-0, gcc-11.2.1, 5.15.32-gentoo-r1 x86_64)
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. warning::
            This suppose the ``qlist`` binary is available and present on the system. We
            do not search for it or try to resolves its canonical path with
            :py:attr:`PackageManager.cli_path <meta_package_manager.base.PackageManager.cli_path>`,
            as we do for the reference ``emerge`` binary.

        .. code-block:: shell-session

            ► qlist --installed --verbose --nocolor
            acct-group/audio-0-r1
            acct-group/cron-0
            app-admin/hddtemp-0.3_beta15-r29
            app-admin/perl-cleaner-2.30
            app-admin/system-config-printer-1.5.16-r1
            app-arch/p7zip-16.02-r8
        """
        # Locate qlist.
        qlist_path = self.search_cli("qlist")
        if not qlist_path:
            raise FileNotFoundError(qlist_path)

        output = self.run_cli(
            "--installed", "--verbose", "--nocolor", override_cli_path=qlist_path
        )

        regexp = re.compile(
            r"""
            (
                ?P<package_id>\S+   # Non-whitespace string...
                (?!-r)              # ...if not directly followred by the "-r" string.
            )
            -                       # A dash.
            (
                ?P<version>[^\s-]+  # Any non-whitespace/non-dash string.
                (?:-r\d+)?          # Optional revision suffix led by a dash (non-grouped).
            )
            """,
            re.VERBOSE,
        )

        for package in output.splitlines():
            match = regexp.match(package)
            if match:
                package_id, installed_version = match.groups()
                yield self.package(id=package_id, installed_version=installed_version)

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            ► emerge --update --deep --pretend --columns --color n --nospinner @world
            [blocks  B     ] app-text/dos2unix
            [ebuild   N    ] app-games/qstat   [25c]
            [ebuild    R   ] sys-apps/sed      [2.4.7-r6]
            [ebuild       U] net-fs/samba      [2.2.8_pre1]      [2.2.7a]
            [ebuild       U] sys-devel/distcc  [2.16]            [2.13-r1] USE=ipv6* -gtk
            [ebuild r     U] dev-libs/icu      [50.1.1:0/50.1.1] [50.1-r2:0/50.1]
            [ebuild r  R   ] dev-libs/libxml2  [2.9.0-r1:2]       USE=icu
        """
        output = self.run_cli(
            "--update",
            "--deep",
            "--pretend",
            "--columns",
            "--color",
            "n",
            "--nospinner",
            "@world",
        )

        regexp = re.compile(
            r"""
            \[.+\]                                  # Update state.
            \                                       # A space.
            (?P<package_id>\S+)                     # Non-whitespace string.
            \s+                                     # Any spacing.
            (?:\[                                   # Non-matching group starting with a '['.
                (?P<latest_version>[^\s\/:]+)       # Any non-spaced string until a ':' or '/' is met.
                \S*                                 # Left-over parts of the version, after a ':' or '/'.
            \])?                                    # Optional group ending with a ']'.
            \s+                                     # Any spacing.
            (?:\[                                   # Non-matching group starting with a '['.
                (?P<installed_version>[^\s\/:]+)    # Any non-spaced string until a ':' or '/' is met.
                \S*                                 # Left-over parts of the version, after a ':' or '/'.
            \])?                                    # Optional group ending with a ']'.
            """,
            re.VERBOSE,
        )

        for package in output.splitlines():
            match = regexp.match(package)
            if match:
                package_id, latest_version, installed_version = match.groups()
                yield self.package(
                    id=package_id,
                    latest_version=latest_version,
                    installed_version=installed_version,
                )

    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. code-block:: shell-session

            ► emerge --search --color n --nospinner blah

            [ Results for search key : blah ]
            Searching...

            *  sys-process/htop
                Latest version available: 1.0.2-r1
                Latest version installed: [ Not Installed ]
                Size of files: 380 KiB
                Homepage:      http://htop.sourceforge.net
                Description:   interactive process viewer
                License:       BSD GPL-2

            *  x11-drivers/nvidia-drivers
                Latest version available: 455.45.01-r1
                Latest version installed: [ Not Installed ]
                Size of files: 180.214 KiB
                Homepage:      https://www.nvidia.com/Download/Find.aspx
                Description:   NVIDIA Accelerated Graphics Driver
                License:       GPL-2 NVIDIA-r2

            [ Applications found : 2 ]

        .. code-block:: shell-session

            ► emerge --search --color n --nospinner %^sed$

        .. code-block:: shell-session

            ► emerge --searchdesc --color n --nospinner sed

        .. code-block:: shell-session

            ► emerge --searchdesc --color n --nospinner %^sed$
        """
        search_param = "--search"
        if extended:
            search_param = "--searchdesc"

        if exact:
            query = f"%^{query}$"

        output = self.run_cli(search_param, "--color", "n", "--nospinner", query)

        regexp = re.compile(
            r"""
            ^\*\s+(?P<package_id>\S+)\n
            \s+Latest\ version\ available:\s+(?P<latest_version>\S+)\n
            (?:\s+.+\n)+?
            \s+Description:\s+(?P<description>.+)\n
            """,
            re.MULTILINE | re.VERBOSE,
        )

        for package_id, version, description in regexp.findall(output):
            yield self.package(
                id=package_id,
                description=description,
                latest_version=version,
            )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            ► sudo emerge --color n --nospinner dev-vcs/git
        """
        return self.run_cli("--color", "n", "--nospinner", package_id, sudo=True)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: shell-session

            ► sudo emerge --update --newuse --deep --color n --nospinner @world
        """
        return self.build_cli(
            "--update",
            "--newuse",
            "--deep",
            "--color",
            "n",
            "--nospinner",
            "@world",
            sudo=True,
        )

    @version_not_implemented
    def upgrade_one_cli(
        self, package_id: str, version: str | None = None
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: shell-session

            ► sudo emerge --update --color n --nospinner dev-vcs/git
        """
        return self.build_cli(
            "--update",
            "--color",
            "n",
            "--nospinner",
            package_id,
            sudo=True,
        )

    def sync(self) -> None:
        """Sync package metadata.

        .. code-block:: shell-session

            ► sudo emerge --sync --color n --nospinner
        """
        self.run_cli("--sync", "--color", "n", "--nospinner", sudo=True)

    def cleanup(self) -> None:
        """Removes things we don't need anymore.

        An update is forced before calling the clean commands, as `pointed to by the emerge documentation <https://wiki.gentoo.org/wiki/Gentoo_Cheat_Sheet#Recommended_method>`_:

        > As a safety measure, depclean will not remove any packages unless *all*
        > required dependencies have been resolved. As a consequence, it is often
        > necessary to run `emerge --update --newuse --deep @world` prior to depclean.

        .. warning::
            This suppose the ``eclean`` binary is available and present on the system. We
            do not search for it or try to resolves its canonical path with
            :py:attr:`PackageManager.cli_path <meta_package_manager.base.PackageManager.cli_path>`,
            as we do for the reference ``emerge`` binary.

        .. code-block:: shell-session

            ► sudo emerge --update --newuse --deep --color n --nospinner @world
            ► sudo emerge --depclean
            ► sudo eclean distfiles
        """
        # Forces an upgrade first, as recommended by emerge documentation.
        self.upgrade()

        self.run_cli("--depclean", sudo=True)

        eclean_path = self.search_cli("eclean")
        if eclean_path:
            self.run_cli("distfiles", override_cli_path=eclean_path, sudo=True)
