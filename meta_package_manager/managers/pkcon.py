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

from extra_platforms import LINUX

from ..capabilities import search_capabilities, version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class Pkcon(PackageManager):
    """PackageKit's console client.

    Documentation:
    - https://www.freedesktop.org/software/PackageKit/
    - https://github.com/PackageKit/PackageKit

    pkcon is an unprivileged client handing transactions to the ``packagekitd``
    daemon over D-Bus, with the distro's native backend (apt, dnf, zypp, alpm, ...)
    doing the real work. Escalation is polkit's job, so no operation is marked
    ``sudo``: under a strict polkit policy, unattended mutations need a policy
    permitting them without interactive authentication.

    .. note::
        pkcon renders packages as a fused ``name-version.arch (repo)`` string and
        never exposes the raw ``name;version;arch;repo`` ID. Names and versions both
        legitimately contain dashes, so the name/version split below anchors on the
        first dash followed by a digit: a documented heuristic, not an exact
        science.
    """

    name = "PackageKit"

    homepage_url = "https://www.freedesktop.org/software/PackageKit/"

    platforms = LINUX

    requirement = ">=0.7.0"
    """All the commands and flags used here (``--plain``, ``--noninteractive``,
    ``--filter``) are present since PackageKit ``0.7.0``."""

    # Keep gettext-localized status words and preamble labels in English so the
    # parsing regexes hold.
    extra_env = {"LC_ALL": "C"}

    # --plain forces the machine-readable output branch even on a terminal.
    post_args = ("--plain",)

    version_regexes = (r"^(?P<version>[\d.]+)$",)
    """
    .. code-block:: shell-session

        $ pkcon --version
        1.3.6
    """

    _RESULT_REGEXP = re.compile(
        r"^(?P<status>\w[\w ]*?) {2,}(?P<blob>\S+) \((?P<repo>[^)]+)\)$",
    )
    """One result line: a status word left-justified to 12 characters, the fused
    package rendering, then the repository in parentheses. The transient progress
    preamble (``Transaction:``, ``Package:``, ``Percentage:`` labels) is
    tab-separated and unparenthesized, so it never matches."""

    _NAME_VERSION_REGEXP = re.compile(r"^(?P<package_id>.+?)-(?P<version>\d.*)$")
    """Split the fused ``name-version`` on the first dash followed by a digit."""

    def _parse_results(self, output: str) -> Iterator[tuple[str, str, str | None]]:
        """Yield ``(status, package_id, version)`` from pkcon result lines.

        The trailing ``.arch`` component is dropped before splitting the name from
        the version.
        """
        for line in output.splitlines():
            match = self._RESULT_REGEXP.match(line)
            if not match:
                continue
            name_version = match.group("blob").rsplit(".", 1)[0]
            split = self._NAME_VERSION_REGEXP.match(name_version)
            if split:
                yield (
                    match.group("status"),
                    split.group("package_id"),
                    split.group("version"),
                )
            else:
                yield match.group("status"), name_version, None

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            $ pkcon get-packages --filter installed --plain
            Installed    gzip-1.12-1.fc38.x86_64 (koji-override-0)
            Installed    hello-2.12.1-2.fc38.x86_64 (fedora)
        """
        output = self.run_cli("get-packages", "--filter", "installed")

        for status, package_id, version in self._parse_results(output):
            if status == "Installed":
                yield self.package(id=package_id, installed_version=version)

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        Result lines carry the update *type* as their status word (``Security``,
        ``Bug fix``, ``Enhancement``, ``Normal``, ...) and the version of the
        pending update.

        .. caution::
            With nothing to update, pkcon prints ``There are no updates available
            at this time.`` and exits ``5`` (``PK_EXIT_CODE_NOTHING_USEFUL``): a
            normal empty result, not a failure, so the error recorded for it is
            discarded.

        .. code-block:: shell-session

            $ pkcon get-updates --plain
            Security     curl-8.0.1-2.fc38.x86_64 (updates)
            Normal       hello-2.12.2-1.fc38.x86_64 (updates)
        """
        errors_before = len(self.cli_errors)
        output = self.run_cli("get-updates")
        if len(self.cli_errors) > errors_before:
            error = self.cli_errors[-1]
            if error.code == 5:
                self.cli_errors.pop()

        for _status, package_id, version in self._parse_results(output):
            yield self.package(id=package_id, latest_version=version)

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. code-block:: shell-session

            $ pkcon search name hello --plain
            Available    hello-2.12.1-2.fc38.x86_64 (fedora)
            Installed    rubygem-mixlib-shellout-3.2.7-3.fc38.noarch (fedora)
        """
        output = self.run_cli("search", "name", query)

        for _status, package_id, version in self._parse_results(output):
            yield self.package(id=package_id, latest_version=version)

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            $ pkcon install --noninteractive hello --plain
        """
        return self.run_cli("install", "--noninteractive", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        .. note::
            With nothing to upgrade this exits ``5`` ("nothing useful was done"),
            which the best-effort maintenance flow reports as a failed manager but
            never as a non-zero mpm exit.

        .. code-block:: shell-session

            $ pkcon update --noninteractive --plain
        """
        return self.build_cli("update", "--noninteractive")

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade one package.

        .. code-block:: shell-session

            $ pkcon update --noninteractive hello --plain
        """
        return self.build_cli("update", "--noninteractive", package_id)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        .. code-block:: shell-session

            $ pkcon remove --noninteractive hello --plain
        """
        return self.run_cli("remove", "--noninteractive", package_id)

    def sync(self) -> None:
        """Refresh the cached repository metadata.

        .. code-block:: shell-session

            $ pkcon refresh --plain
        """
        self.run_cli("refresh")
