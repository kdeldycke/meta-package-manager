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

from typing import ClassVar

from extra_platforms import LINUX

from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


_ROW_MARKER = "◆"
"""Character opening every application row, and nothing else in the listing."""

_NAME_COLUMN = "APPNAME"
_VERSION_COLUMN = "VERSION"
"""Header labels the column layout is read from, rather than assumed."""

_DECORATIONS = "*🔒✓✖ "
"""Marks the listing appends to a name or a version, carrying state rather than
identity: an asterisk for an archived or obsolete application, a padlock for a
locked or sandboxed one, and a tick or cross for the checksum verdict.
"""


class AM(PackageManager):
    """AppImage manager, covering the applications of its own catalog.

    ```{note}
    `am` and `appman` are the same script under two names, and only this one is
    wrapped. AppMan's repository holds no implementation at all, just a stub
    that replaces itself with this script, which then reads its own path to
    decide whether to run system-wide or under the user's home. Wrapping both
    would double-count: `am -fi` renders AppMan's applications in a second
    table of its own whenever AppMan is configured, so they are already
    reported here. See {doc}`/unsupported` for the recorded decision.
    ```

    ```{caution}
    The listing's column count depends on its contents: a fifth column appears
    between the name and the version whenever an application resolves to a
    third-party catalog. The version is therefore located by reading the header
    rather than by counting from the left, which is also what lets a listing
    carrying two tables be parsed in one pass.
    ```

    ```{note}
    No `install`. `am` refuses to be run under `sudo` and escalates on its own
    instead, priming the credential cache before it installs anything, so an
    install blocks on a password prompt that no flag of its own can answer.
    Removal is unaffected, `-R` needing no confirmation and no escalation mpm
    has to arrange.

    No `outdated` either: nothing reports a remote version without installing
    it, and the catalog carries no versions at all. Its maintainer declined to
    publish a machine-readable feed, so this is settled rather than pending, and
    `upgrade --all` is unaffected.

    No `search`: results are folded to the terminal width before they are
    printed, so a record wraps across lines with no marker to rejoin it, and its
    description is unrecoverable once wrapped.
    ```

    Documentation: [AM](https://github.com/ivan-hc/AM).
    """

    name = "AppImage Manager"

    homepage_url = "https://github.com/ivan-hc/AM"

    platforms = LINUX

    sudo = False
    default_sudo = False
    """`am` refuses outright to run under `sudo`, exiting rather than
    proceeding, and arranges its own escalation per privileged step instead.
    """

    internal_sudo = True
    """It calls the escalation binary itself for the steps that need it, picking
    `sudo` or `doas` from what the host provides.
    """

    requirement = ">=10.4"
    """The release that added the flag answering its confirmation prompts, which
    is what makes the mutating operations here unattended.
    """

    extra_env: ClassVar = {
        # Belt and braces: `am` already drops its colouring when its output is
        # not a terminal, and honours this on top of that.
        "NO_COLOR": "1",
    }

    version_cli_options = ("--version",)

    version_regexes = (r"(?m)^(?P<version>\d+(?:\.\d+)+)$",)
    r"""Search a line holding nothing but the version.

    ```{code-block} shell-session

    $ am --version
    10.4
    ```

    Anchored to a whole line because `am` prepends a multi-line warning banner
    on hosts that restrict user namespaces, which is the default on recent
    Ubuntu: a pattern matching the first number anywhere would read that banner
    instead.
    """

    def _parse_listing(self, output: str) -> Iterator[Package]:
        """Yield one package per application row of a listing.

        Reads each table's header to locate the version column, so a listing
        holding both this manager's applications and AppMan's is parsed in one
        pass even when the two carry a different number of columns.
        """
        version_index: int | None = None
        for line in output.splitlines():
            cells = [cell.strip() for cell in line.split("|")]

            # A header re-declares the layout for every row that follows it.
            if _NAME_COLUMN in cells[0]:
                version_index = (
                    cells.index(_VERSION_COLUMN) if _VERSION_COLUMN in cells else None
                )
                continue

            if not line.lstrip().startswith(_ROW_MARKER):
                continue

            package_id = cells[0].lstrip(_ROW_MARKER).strip(_DECORATIONS)
            if not package_id:
                continue

            version = None
            if version_index is not None and len(cells) > version_index:
                version = cells[version_index].strip(_DECORATIONS) or None

            yield self.package(id=package_id, installed_version=version)

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        `-fi` is the listing without the trailing table of unmanaged AppImages,
        and `--byname` fixes its order, which is otherwise by size.

        ```{code-block} shell-session

        $ am -fi --byname

         YOU HAVE INSTALLED 3 PROGRAMS MANAGED BY "AM"

         - APPNAME              | VERSION             | TYPE           | SIZE
         - -------              | -------             | ----           | ----
         ◆ code                 | 1.107.1             | dynamic-binary | 450 MiB
         ◆ krita                | 5.2.14              | appimage       | 322 MiB
         ◆ zoom                 | 6.4.3.827.glibc2.27 | appimage*      | 288 MiB
        ```

        ```{note}
        A version is genuinely optional here: an application whose updater
        reports none renders an empty cell, and one is yielded without a version
        rather than with a placeholder.
        ```
        """
        yield from self._parse_listing(self.run_cli("-fi", "--byname"))

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        `--apps` confines the run to the installed applications. The bare form
        additionally refreshes the catalogs and rewrites the `am` script
        itself, which is not what upgrading packages should mean.

        ```{code-block} shell-session

        $ am -y -u --apps
        ```
        """
        return self.build_cli("-y", "-u", "--apps")

    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the package provided as parameter.

        Naming an application genuinely restricts the run to it.

        ```{code-block} shell-session

        $ am -y -u firefox
        ```
        """
        return self.build_cli("-y", "-u", package_id)

    def remove(self, package_id: str) -> str:
        """Removes a package.

        `-R` is the unattended removal: unlike its lowercase counterpart it asks
        for no confirmation, so no flag is needed to answer one.

        ```{code-block} shell-session

        $ am -R firefox
        ```
        """
        return self.run_cli("-R", package_id)

    def cleanup_cache(self) -> None:
        """Removes things we don't need anymore.

        Clears the download caches, the caches applications leave in the home
        directory, and the launchers left behind by removals.

        ```{code-block} shell-session

        $ am -c
        ```
        """
        self.run_cli("-c")
