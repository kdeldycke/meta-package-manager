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

from extra_platforms import CYGWIN

from ..capabilities import search_capabilities, version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class APT_Cyg(PackageManager):
    """The apt-cyg package manager for Cygwin.

    Documentation:
    - https://github.com/transcode-open/apt-cyg

    .. note::
        apt-cyg is a single bash script wrapping Cygwin's package repository. Cygwin
        has no root/sudo concept: every operation runs as the invoking user.

    .. note::
        The listing commands print bare package names with no version column, so
        installed packages are yielded without an ``installed_version``. apt-cyg has
        no upgrade, outdated or cache-cleaning command at all: packages are upgraded
        by re-running Cygwin's own ``setup`` program.
    """

    name = "apt-cyg"

    homepage_url = "https://github.com/transcode-open/apt-cyg"

    platforms = CYGWIN

    version_regexes = (r"apt-cyg version (?P<version>\S+)",)
    """apt-cyg is effectively unversioned: the only version signal is the hardcoded
    literal in its usage text, which has always reported ``1``.

    .. code-block:: shell-session

        $ apt-cyg --version
        apt-cyg version 1

        The MIT License (MIT)

        Copyright (c) 2005-9 Stephen Jungels
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        The output format is derived from the script's own ``apt-list``
        implementation (``awk 'NR>1 && $0=$1' /etc/setup/installed.db``): the
        ``INSTALLED.DB`` header is skipped and one bare package name is printed per
        line, without any version.

        .. code-block:: shell-session

            $ apt-cyg list
            bash
            coreutils
            tree
        """
        output = self.run_cli("list")

        for line in output.splitlines():
            package_id = line.strip()
            if package_id:
                yield self.package(id=package_id)

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        ``listall`` greps the downloaded ``setup.ini`` catalog (populated by
        ``apt-cyg update``) and prints one bare matching package name per line.

        .. caution::
            The query is interpreted as a regular expression by apt-cyg, and results
            carry no version or description: exact and extended matching are
            refiltered by
            :py:meth:`meta_package_manager.manager.PackageManager.refiltered_search`.

        .. code-block:: shell-session

            $ apt-cyg listall tree
            tree
        """
        output = self.run_cli("listall", query)

        for line in output.splitlines():
            package_id = line.strip()
            if package_id:
                yield self.package(id=package_id)

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            $ apt-cyg install tree
        """
        return self.run_cli("install", package_id)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        .. code-block:: shell-session

            $ apt-cyg remove tree
        """
        return self.run_cli("remove", package_id)

    def sync(self) -> None:
        """Refresh the ``setup.ini`` package catalog from the configured mirror.

        .. code-block:: shell-session

            $ apt-cyg update
        """
        self.run_cli("update")
