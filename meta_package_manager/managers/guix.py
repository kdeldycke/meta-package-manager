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


class Guix(PackageManager):
    """GNU Guix functional package manager.

    .. note::
        All operations target the current user's default profile. Declarative
        system configuration (Guix System ``config.scm``) is not covered.
    """

    homepage_url = "https://guix.gnu.org"

    platforms = LINUX_LIKE

    requirement = ">=1.0.0"

    version_regexes = (r"guix \(GNU Guix\) (?P<version>\S+)",)
    """
    .. code-block:: shell-session

        $ guix --version
        guix (GNU Guix) 1.4.0
    """

    _SEARCH_FIELD_REGEXP = re.compile(
        r"^(?P<field>\w[\w-]*):\s+(?P<value>.+)$",
    )
    """Match a single recutils field line (``name: value``)."""

    _OUTDATED_REGEXP = re.compile(
        r"^\s+(?P<package_id>\S+)\s+(?P<installed_version>\S+)\s+→\s+(?P<latest_version>\S+)\s*$",
        re.MULTILINE,
    )
    """Match an upgrade line from ``guix upgrade --dry-run``.

    Sample output::

        The following packages would be upgraded:
           hello 2.12.1 → 2.12.3
           sed   4.8 → 4.9
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        Output is tab-separated: name, version, output, store path.

        .. code-block:: shell-session

            $ guix package --list-installed
            hello	2.10	out	/gnu/store/...-hello-2.10
            python	3.10.7	out	/gnu/store/...-python-3.10.7
        """
        output = self.run_cli("package", "--list-installed")

        for line in output.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                yield self.package(
                    id=parts[0],
                    installed_version=parts[1],
                )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        Relies on ``guix upgrade --dry-run`` which lists every package that
        would be upgraded without modifying the user profile.

        .. code-block:: shell-session

            $ guix upgrade --dry-run
            The following packages would be upgraded:
               hello 2.12.1 → 2.12.3
               sed   4.8 → 4.9
        """
        output = self.run_cli("upgrade", "--dry-run")

        for match in self._OUTDATED_REGEXP.finditer(output):
            yield self.package(
                id=match.group("package_id"),
                installed_version=match.group("installed_version"),
                latest_version=match.group("latest_version"),
            )

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. caution::
            Search does not support extended or exact matching. So we return
            the best subset of results and let
            :py:meth:`meta_package_manager.base.PackageManager.refiltered_search`
            refine them.

        Results are printed in recutils format with records separated by blank
        lines.

        .. code-block:: shell-session

            $ guix search hello
            name: hello
            version: 2.10
            outputs: out
            systems: x86_64-linux i686-linux
            dependencies: glibc@2.35 ...
            location: gnu/packages/base.scm:86:2
            homepage: https://www.gnu.org/software/hello/
            license: GPL 3+
            synopsis: Hello, GNU world: an example GNU package
            description: GNU Hello prints the message "Hello, world!"
            + and then exits.  It serves as an example of standard
            + GNU coding practices.
            relevance: 10

        """
        output = self.run_cli("search", query)

        for record in re.split(r"\n\n+", output.strip()):
            fields: dict[str, str] = {}
            for line in record.splitlines():
                match = self._SEARCH_FIELD_REGEXP.match(line)
                if match:
                    fields[match.group("field")] = match.group("value")
                # Continuation lines (``+ ...``) are ignored; we only need the
                # first line of multi-line fields like description.

            name = fields.get("name")
            if name:
                yield self.package(
                    id=name,
                    description=fields.get("synopsis"),
                    latest_version=fields.get("version"),
                )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            $ guix install hello
        """
        return self.run_cli("install", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        .. code-block:: shell-session

            $ guix upgrade
        """
        return self.build_cli("upgrade")

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade one package.

        .. code-block:: shell-session

            $ guix upgrade hello
        """
        return self.build_cli("upgrade", package_id)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        .. code-block:: shell-session

            $ guix remove hello
        """
        return self.run_cli("remove", package_id)

    def sync(self) -> None:
        """Fetch the latest Guix channel revisions.

        .. code-block:: shell-session

            $ guix pull
        """
        self.run_cli("pull")

    def cleanup(self) -> None:
        """Collect garbage in the store.

        .. code-block:: shell-session

            $ guix gc
        """
        self.run_cli("gc")
