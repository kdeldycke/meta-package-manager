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
from typing import ClassVar

from extra_platforms import SLITAZ

from ..capabilities import search_capabilities, version_not_implemented
from ..execution import CLIError
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from ..package import Package


class Tazpkg(PackageManager):
    """SliTaz GNU/Linux's package manager.

    The code also lives in a git clone,
    [SliTaz-official/tazpkg](https://github.com/SliTaz-official/tazpkg).

    """

    maintenance_note = (
        "[SliTaz](https://slitaz.org) has published no stable ISO since 5.0 (2023) "
        "but shows active development into 2026; `tazpkg` remains its native package "
        "manager."
    )

    name = "TazPkg"

    homepage_url = "https://slitaz.org"
    documentation_url = "https://doc.slitaz.org/en:handbook:tazpkg"
    repository_url = "https://hg.slitaz.org/tazpkg"
    wikipedia_url = "https://en.wikipedia.org/wiki/SliTaz"

    keywords = ("slitaz",)

    platforms = SLITAZ

    default_sudo = True
    privileged_operations = frozenset(
        {"cleanup", "install", "remove", "sync", "upgrade", "upgrade_all"},
    )

    # Keep gettext-localized headers and prompts in English.
    extra_env: ClassVar = {"LC_ALL": "C"}

    # Render titles, separators and markers as plain text instead of ANSI-decorated.
    post_args = ("--output=raw",)

    version_cli = "awk"
    """tazpkg has no version command at all: its own version only exists as the
    `tazpkg` row of the installed-packages database. This probe mirrors, verbatim,
    how tazpkg resolves its `VERSION` variable for itself::

        export VERSION=$(awk -F$'\\t' '$1=="tazpkg"{print $2}' \\
            "$PKGS_DB/installed.info")
    """

    version_cli_options = (
        "-F\t",
        '$1=="tazpkg"{print $2}',
        "/var/lib/tazpkg/installed.info",
    )

    version_regexes = (r"^(?P<version>[\d.]+)$",)
    """A bare integer Mercurial revision on cooking releases (`944`) or a dotted
    version on stable ones (`4.9.2`)."""

    _SELF_UPGRADE_REFUSAL = "You need upgrade tazpkg first"
    """What TazPkg prints, with exit code `0`, when it refuses an install until it
    has upgraded itself. `LC_ALL=C` keeps it in English."""

    _ANSI_REGEXP = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

    _PACKAGE_LINE_REGEXP = re.compile(
        r"^(?P<package_id>\S+)\s+(?P<version>\d\S*)\s+\S+\s*$",
    )
    """Data rows are "name version category" triples whose version starts with a
    digit: titles, `===`/`---` separators and "N packages ..." footers all fail
    that shape."""

    def _parse_listing(self, output: str) -> Iterator[tuple[str, str]]:
        """Yield `(package_id, version)` from a decorated tazpkg listing."""
        for line in self._ANSI_REGEXP.sub("", output).splitlines():
            match = self._PACKAGE_LINE_REGEXP.match(line)
            if match:
                yield match.group("package_id"), match.group("version")

    def _raise_self_upgrade_refusal(self, output: str) -> None:
        """Raise the refusal TazPkg reports with exit code `0` while it waits to
        upgrade itself.

        The failure is relayed at `WARNING` and recorded in
        {attr}`~meta_package_manager.execution.CLIExecutor.cli_errors`, as the
        executor's own failure gate does for a non-zero exit.
        """
        if self._SELF_UPGRADE_REFUSAL not in output:
            return
        exception = CLIError(
            0,
            output,
            "TazPkg refuses to install packages until it upgrades itself: "
            "run `tazpkg get-install tazpkg --forced`, then try again.",
        )
        self._relay_failure(exception, is_escalation=False)
        self.cli_errors.append(exception)
        raise exception

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        Captured on a minimal SliTaz 5.0 system, holding `tazpkg` and its
        dependencies alone.

        ```{code-block} shell-session

        $ tazpkg list --output=raw

        List of all installed packages
        ================================================================================
        busybox                            1.37.0            base-system
        gettext-base                       0.21              base-system
        glibc-base                         2.20              base-system
        ncurses-common                     6.4               base-system
        slitaz-base-files                  348               base-system
        tazpkg                             5.9.5             base-system
        ================================================================================
        6 packages installed.
        ```
        """
        output = self.run_cli("list")

        for package_id, version in self._parse_listing(output):
            yield self.package(id=package_id, installed_version=version)

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        tazpkg matches the query as a case-insensitive substring of
        `name-version`, and answers in two sections: the installed matches, then
        the mirror's. Only the mirror section is read, since it lists every match
        once, at the version `get-install` fetches. Reading both would report an
        installed package twice.

        ```{code-block} shell-session

        $ tazpkg search nano --output=raw

        Search result for "nano"
        ================================================================================
        Installed packages
        --------------------------------------------------------------------------------
        nano                    9.0               utilities
        nanochess               1.0               games
        ================================================================================
        2 installed packages found for "nano"

        Available packages
        --------------------------------------------------------------------------------
        nano                    9.0               utilities
        nano-doc                9.0               utilities
        nano-lang               9.0               utilities
        nanochess               1.0               games
        nanoshot                0.2.15            utilities
        ================================================================================
        5 available packages found for "nano"
        ```
        """
        output = self.run_cli("search", query)

        # Without a mirror section, the whole output is read.
        _, marker, available = output.partition("Available packages")
        for package_id, version in self._parse_listing(available if marker else output):
            yield self.package(id=package_id, latest_version=version)

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package from the mirror.

        `--forced` skips the already-installed guard, keeping the call
        non-interactive.

        SliTaz's `check_tazpkgupg.sh` boot script creates
        `/var/lock/tazpkgup.lock` when the mirror has a newer TazPkg. While that
        lock exists, TazPkg refuses to install anything but itself, prints
        `You need upgrade tazpkg first !` and exits `0`. That refusal is raised
        as an error naming the command to run first.

        ```{code-block} shell-session

        $ sudo tazpkg get-install nano --forced --output=raw
        ```
        """
        output = self.run_cli("get-install", package_id, "--forced", sudo=True)
        self._raise_self_upgrade_refusal(output)
        return output

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        `-i` (no long form) auto-confirms, upgrading every outdated package; the
        command recharges the package lists first.

        ```{code-block} shell-session

        $ sudo tazpkg up -i --output=raw
        ```
        """
        return self.build_cli("up", "-i", sudo=True)

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade one package.

        tazpkg has no per-package upgrade verb: its own upgrade loop re-runs
        `get-install --forced` on each outdated package.

        ```{code-block} shell-session

        $ sudo tazpkg get-install nano --forced --output=raw
        ```
        """
        return self.build_cli("get-install", package_id, "--forced", sudo=True)

    def upgrade(
        self,
        package_id: str | None = None,
        version: str | None = None,
        *,
        outdated_ids: Iterable[str] | None = None,
    ) -> str:
        """Upgrade one or all packages, and raise TazPkg's self-upgrade refusal.

        Both commands run `get-install`, so the lock that stops
        {meth}`install` stops them too. `up -i` keeps going after a refusal:
        it skips the packages its list places before `tazpkg`, upgrades
        `tazpkg`, which deletes the lock, then upgrades the rest.
        """
        output = super().upgrade(package_id, version, outdated_ids=outdated_ids)
        self._raise_self_upgrade_refusal(output)
        return output

    def remove(self, package_id: str) -> str:
        """Remove one package.

        No `--auto` on purpose: it would also auto-confirm the "remove
        dependents?" follow-up and cascade. On a non-terminal stdout (mpm's
        subprocess pipe) the `(y/N)` prompt is skipped and only the target
        package is removed.

        ```{code-block} shell-session

        $ sudo tazpkg remove nano --output=raw
        ```
        """
        return self.run_cli("remove", package_id, sudo=True)

    def sync(self) -> None:
        """Recharge the package lists from the mirror.

        ```{code-block} shell-session

        $ sudo tazpkg recharge --output=raw
        ```
        """
        self.run_cli("recharge", sudo=True)

    def cleanup_cache(self) -> None:
        """Delete every downloaded package from the cache.

        ```{code-block} shell-session

        $ sudo tazpkg clean-cache --output=raw
        ```
        """
        self.run_cli("clean-cache", sudo=True)
