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

from ..base import PackageManager
from ..capabilities import version_not_implemented

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..base import Package


class CPAN(PackageManager):
    """The Comprehensive Perl Archive Network package manager.

    .. tip::

        Installs may require ``sudo`` when using the system Perl. Consider using
        ``local::lib`` for user-local installs.

    .. caution::

        On first run, ``cpan`` may launch an interactive configuration. This is
        suppressed by the ``PERL_MM_USE_DEFAULT`` environment variable.
    """

    name = "Perl's CPAN"

    homepage_url = "https://www.cpan.org"

    platforms = ALL_PLATFORMS

    requirement = ">=1.64"
    """
    .. code-block:: shell-session

        $ cpan -v
        >(info): /usr/bin/cpan script version 1.676, CPAN.pm version 2.28
    """

    extra_env = {"PERL_MM_USE_DEFAULT": "1"}  # noqa: RUF012
    """Suppress interactive prompts during install and configuration."""

    version_cli_options = ("-v",)

    version_regexes = (r"CPAN\.pm\s+version\s+(?P<version>\S+)",)
    """
    .. code-block:: shell-session

        $ cpan -v
        >(info): /usr/bin/cpan script version 1.676, CPAN.pm version 2.28
    """

    _INSTALLED_REGEXP = re.compile(r"^(?P<package_id>\S+)\t(?P<version>\S+)$")

    _OUTDATED_REGEXP = re.compile(
        r"^(?P<package_id>\S+)\s+(?P<installed_version>\S+)\s+(?P<latest_version>\S+)$",
    )

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            $ cpan -l 2>/dev/null
            Loading internal logger. Log::Log4perl recommended for better logging
            O	1.03
            Errno	1.33
            Config	5.034001
            Encode	3.08_01
            meta_notation	undef
        """
        output = self.run_cli("-l")

        for line in output.splitlines():
            match = self._INSTALLED_REGEXP.match(line)
            if match:
                package_id = match.group("package_id")
                version = match.group("version")
                yield self.package(
                    id=package_id,
                    installed_version=version if version != "undef" else None,
                )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            $ cpan -O 2>/dev/null
            Loading internal logger. Log::Log4perl recommended for better logging
            Reading '/Users/kde/.cpan/Metadata'
              Database was generated on Thu, 26 Mar 2026 13:41:03 GMT
            Module Name                                Local    CPAN
            ---------------------------------------------------------------
            Algorithm::C3                             0.1000  0.1100
            Archive::Tar                              2.3800  3.0400
            App::Cpan                                 1.6760  1.6780
        """
        output = self.run_cli("-O")

        for line in output.splitlines():
            match = self._OUTDATED_REGEXP.match(line)
            if match:
                package_id = match.group("package_id")
                installed_version = match.group("installed_version")
                latest_version = match.group("latest_version")
                yield self.package(
                    id=package_id,
                    installed_version=installed_version,
                    latest_version=latest_version,
                )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            $ cpan JSON
        """
        return self.run_cli(package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        .. code-block:: shell-session

            $ cpan -u
        """
        return self.build_cli("-u")

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade one package.

        .. code-block:: shell-session

            $ cpan -i JSON
        """
        return self.build_cli("-i", package_id)
