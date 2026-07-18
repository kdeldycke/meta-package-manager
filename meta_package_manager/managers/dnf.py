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

from extra_platforms import UNIX_WITHOUT_MACOS

from ..capabilities import search_capabilities, version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class DNF(PackageManager):
    """Fedora's RPM package manager.

    ``mpm`` reads the inventory through ``repoquery`` rather than the human-facing
    listing: ``--userinstalled`` for packages installed on request (dependencies
    pulled in automatically are skipped) and ``--upgrades`` for pending updates,
    both with a ``--queryformat`` that joins the fields on a private ``___MPM___``
    delimiter so summaries containing spaces stay splittable. Every call is forced
    ``--color=never`` and ``--quiet`` for parseable output.

    .. note::
        ``remove`` runs ``autoremove``, so removing a package also drops the
        dependencies it leaves orphaned. ``search`` matches names only, with no
        exact or extended mode.

    The ``DNF5`` and ``YUM`` subclasses reuse everything here, differing only in
    the binary and forced arguments.

    Documentation:

    - https://dnf.readthedocs.io/en/latest/command_ref.html
    - https://wiki.archlinux.org/title/Pacman/Rosetta (command equivalences)
    """

    name = "Fedora DNF"

    homepage_url = "https://github.com/rpm-software-management/dnf"

    platforms = UNIX_WITHOUT_MACOS

    default_sudo = True

    requirement = ">=4.0.0"

    cli_names: tuple[str, ...] = ("dnf", "dnf4")
    """
    .. code-block:: shell-session

        $ dnf --version
        4.9.0
    """

    pre_args: tuple[str, ...] = ("--color=never", "--quiet")

    _SEARCH_REGEXP = re.compile(r"(\S+)\.\S+\s:\s(\S+)")

    DELIMITER = "___MPM___"

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            $ dnf repoquery --userinstalled --qf FORMAT
            acl___MPM___2.2.53-1.el8___MPM___Access control list utilities___MPM___x86_64
            audit___MPM___3.0.7-4.el9___MPM___User space auditing tools___MPM___x86_64
            audit-libs___MPM___3.0.7-4.el9___MPM___Dynamic auditing library___MPM___x86_64
        """
        qf = ["%{name}", "%{version}", "%{summary}", "%{arch}\n"]
        output = self.run_cli(
            "repoquery", "--userinstalled", "--qf", DNF.DELIMITER.join(qf)
        )

        for line_package in output.splitlines():
            # remove empty new line
            if not line_package:
                continue
            package_id, installed_version, summary, arch = line_package.split(
                DNF.DELIMITER
            )
            yield self.package(
                id=package_id,
                description=summary,
                installed_version=installed_version,
                arch=arch,
            )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            $ dnf repoquery --upgrades --qf FORMAT
            acl___MPM___2.2.53-1.el8___MPM___2.6.53-1.el8___MPM___Access control list utilities___MPM___x86_64
            audit___MPM___2.2.53-1.el8___MPM___2.5.53-1.el8___MPM___User space auditing tools___MPM___x86_64
            audit-libs___MPM___2.2.53-1.el8___MPM___2.6.53-1.el8___MPM___Dynamic auditing library___MPM___x86_64
        """
        qf = ["%{name}", "%{version}", "%{evr}", "%{summary}", "%{arch}\n"]
        output = self.run_cli("repoquery", "--upgrades", "--qf", DNF.DELIMITER.join(qf))

        for line_package in output.splitlines():
            # remove empty new line
            if not line_package:
                continue
            package_id, installed_version, last_version, summary, arch = (
                line_package.split(DNF.DELIMITER)
            )
            yield self.package(
                id=package_id,
                description=summary,
                installed_version=installed_version,
                arch=arch,
                latest_version=last_version,
            )

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. caution::
            Search does not support extended or exact matching. So we return the best
            subset of results and let
            :py:meth:`meta_package_manager.manager.PackageManager.refiltered_search` refine
            them.

        .. code-block:: shell-session

            $ dnf --color=never search usd
            Last metadata expiration check: 0:06:37 ago on Sun 03 Apr 2022.
            =================== Name Exactly Matched: usd =====================
            usd.aarch64 : 3D VFX pipeline interchange file format
            =================== Name & Summary Matched: usd ===================
            python3-usd.aarch64 : Development files for USD
            usd-devel.aarch64 : Development files for USD
            ======================= Name Matched: usd =========================
            lvm2-dbusd.noarch : LVM2 D-Bus daemon
            usd-libs.aarch64 : Universal Scene Description library
        """
        output = self.run_cli("search", query)

        for line in output.splitlines()[1:]:
            # Skip section headers.
            if line.startswith("="):
                continue

            # Extract package ID and description.
            match = self._SEARCH_REGEXP.match(line)
            if match:
                package_id, description = match.groups()
                yield self.package(id=package_id, description=description)

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            $ sudo dnf --color=never --quiet --assumeyes install pip
        """
        return self.run_cli("--assumeyes", "install", package_id, sudo=True)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all outdated packages.

        .. code-block:: shell-session

            $ sudo dnf --color=never --quiet --assumeyes upgrade
        """
        return self.build_cli("--assumeyes", "upgrade", sudo=True)

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the provided package.

        .. code-block:: shell-session

            $ sudo dnf --color=never --quiet --assumeyes upgrade pip
        """
        return self.build_cli("--assumeyes", "upgrade", package_id, sudo=True)

    def remove(self, package_id: str) -> str:
        """Remove one package and one only.

        .. code-block:: shell-session

            $ sudo dnf --color=never --quiet --assumeyes autoremove package_id
        """

        return self.run_cli("--assumeyes", "autoremove", package_id, sudo=True)

    def sync(self) -> None:
        """Sync package metadata.

        .. code-block:: shell-session

            $ dnf --color=never --quiet check-update
        """
        self.run_cli("check-update")

    def cleanup(self) -> None:
        """Removes things we don't need anymore.

        .. code-block:: shell-session

            $ sudo dnf --color=never --quiet --assumeyes autoremove
            $ dnf --color=never --quiet clean all
        """
        self.run_cli("--assumeyes", "autoremove", sudo=True)
        self.run_cli("clean", "all")


class DNF5(DNF):
    """The ``dnf5`` rewrite of DNF, Fedora's reference package manager since
    Fedora 41.

    Inherits every operation and parser from ``DNF``. Its forced arguments drop
    ``--color=never`` (``dnf5`` rejects that option), keeping only ``--quiet``.
    """

    name = "Fedora DNF5"

    homepage_url = "https://github.com/rpm-software-management/dnf5"

    requirement = ">=5.0.0"
    """dnf5 is the new reference package manager as of Fedora 41."""

    cli_names = ("dnf5",)

    pre_args = ("--quiet",)
    """Reset global options inherited from the `DNF` above.

    `dnf5` does not support `--color=never` parameter.
    """


class YUM(DNF):
    """YUM, the package manager DNF superseded.

    On current Fedora and RHEL the ``yum`` binary is a wrapper around ``dnf``.
    ``mpm`` drives it exactly as ``DNF``, only the binary name differs.
    """

    name = "Fedora YUM"

    homepage_url = "http://yum.baseurl.org"

    cli_names = ("yum",)
