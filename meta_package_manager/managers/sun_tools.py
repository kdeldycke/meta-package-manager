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

from extra_platforms import SOLARIS

from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class Sun_Tools(PackageManager):
    """Solaris' legacy System V Release 4 packaging tools.

    Documentation:

    - https://docs.oracle.com/cd/E86824_01/html/E54763/pkginfo-1.html
    - https://docs.oracle.com/cd/E26502_01/html/E29031/pkgadd-1m.html
    - https://docs.oracle.com/cd/E26502_01/html/E29031/pkgrm-1m.html

    The suite spans several binaries: ``pkginfo`` (the read-only query tool, used as
    the main CLI), ``pkgadd`` and ``pkgrm``.

    .. note::
        SVR4 packages come from local media or datastream files, not a network
        repository: there is no catalog to search, refresh or diff against, and
        ``pkgadd`` installs a specific local artifact rather than resolving a name.
        Only ``installed`` and ``remove`` are therefore implemented; Solaris 11's
        modern repository-based interface is IPS (``pkg``), a different manager.
    """

    name = "Solaris SVR4 package tools"

    homepage_url = "https://docs.oracle.com/cd/E86824_01/html/E54763/pkginfo-1.html"

    platforms = SOLARIS

    default_sudo = True

    cli_names = ("pkginfo",)

    # pkgrm lives in /usr/sbin, which is not always on a regular user's PATH.
    cli_search_path = ("/usr/sbin",)

    version_cli = "uname"
    """None of the SVR4 tools has a version flag: ``pkginfo -v`` matches a package
    *version* and ``pkgadd``/``pkgrm`` only take ``-v`` as verbose. The suite ships
    with the base system, so its version is the OS release reported by ``uname -r``
    (``5.11`` on Solaris 11).
    """

    version_cli_options = ("-r",)

    version_regexes = (r"(?P<version>[\d.]+)",)
    """
    .. code-block:: shell-session

        $ uname -r
        5.11
    """

    _PKGINFO_FIELD_REGEXP = re.compile(
        r"^\s*(?P<field>PKGINST|VERSION|STATUS):\s+(?P<value>.+?)\s*$",
    )

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        Plain ``pkginfo`` prints no version column (only category, package instance
        and name), so the long ``-l`` listing is parsed instead: each package is a
        multi-line block carrying ``PKGINST:``, ``VERSION:`` and ``STATUS:`` fields.
        Only completely-installed packages are yielded.

        .. code-block:: shell-session

            $ pkginfo -l
              PKGINST:  SUNWcar
                  NAME:  Core Architecture, (Root)
              CATEGORY:  system
                  ARCH:  i386.i86pc
               VERSION:  11.10.0,REV=2005.01.21.16.34
               BASEDIR:  /
                VENDOR:  Oracle Corporation
                STATUS:  completely installed
        """
        output = self.run_cli("-l")

        package_id = None
        version = None
        complete = False
        for line in output.splitlines():
            match = self._PKGINFO_FIELD_REGEXP.match(line)
            if not match:
                continue
            field, value = match.group("field"), match.group("value")
            if field == "PKGINST":
                # A new block starts: flush the previous one.
                if package_id and complete:
                    yield self.package(id=package_id, installed_version=version)
                package_id = value
                version = None
                complete = False
            elif field == "VERSION":
                version = value
            elif field == "STATUS":
                complete = value.startswith("completely installed")
        if package_id and complete:
            yield self.package(id=package_id, installed_version=version)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        ``-n`` runs non-interactively: pkgrm exits instead of prompting, so a
        removal requiring interaction (like a dependency confirmation) fails fast
        rather than hanging mpm's subprocess.

        .. code-block:: shell-session

            $ sudo pkgrm -n SUNWzlib
        """
        pkgrm_path = self.sibling_cli("pkgrm")
        return self.run_cli(
            "-n",
            package_id,
            override_cli_path=pkgrm_path,
            sudo=True,
        )
