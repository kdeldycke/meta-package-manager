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

from extra_platforms import LINUX_LIKE, MACOS, WINDOWS

from ..capabilities import version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


_ANSI_REGEXP = re.compile(r"\x1b\[[0-9;]*m")
"""Style sequences to strip before parsing the update report.

bin colors its two streams through separate libraries, and only one of them
honors `NO_COLOR`. That one is `fatih/color`, governing the version strings; the
`caarlos0/log` lines carrying them are styled independently and keep their color
whenever `CI` is non-empty, which every GitHub Actions run sets. The escape lands
on the bullet the pattern anchors on, so it is removed rather than matched
around.
"""

DRY_RUN_UPDATES_FOUND = 3
"""Exit code `bin update --dry-run` uses to report that updates exist.

A dry run finding nothing exits `0`, and finding something exits this instead,
so neither is a failure. Anything else is.
"""


class Bin(PackageManager):
    """Installer of binaries straight from GitHub releases and similar sources.

    ```{caution}
    The package identifier is the absolute path of the installed binary, which is
    what `list` reports and what `remove` and `update` accept. That choice is
    forced rather than preferred: bin names a package differently depending on
    the verb. Installing takes a source spec (`github.com/junegunn/fzf`, a
    release-tag URL, `goinstall://…`, `docker://…`, a vendor host), while
    everything afterwards is keyed on the installed path. Handing a source spec
    back to `remove` does not resolve, and a bare basename resolves through
    `$PATH` first, so a managed binary shadowed by another copy on `$PATH` fails
    outright. The absolute path is the only identifier every non-installing
    operation accepts.
    ```

    ```{note}
    That asymmetry is also why `install` is not implemented: no identifier `list`
    reports can be handed to it, so `mpm` could never install what it had just
    listed. Installing through bin stays a `bin install <spec>` the user runs
    themselves, and `mpm` reports and maintains the result.

    No `search`: bin has no registry to search, only sources the user names. No
    `sync`: there is no index to refresh. `bin prune` is left alone too, since it
    drops configuration entries whose file has vanished rather than cleaning up
    packages.
    ```

    ```{caution}
    A bin that has never been configured prompts for its download directory on
    *every* command, the listing included, and cannot be driven until someone
    answers once interactively. `mpm` sees that as a failed version probe and
    treats the manager as unavailable, which is the right outcome: an
    uninitialised bin has no inventory to report, and reporting zero packages
    would be a lie.
    ```

    No escalation: bin installs into a directory it picked from `$PATH` for being
    writable, and never needs root.

    Documentation: [bin](https://github.com/marcosnils/bin).
    """

    name = "bin"

    homepage_url = "https://github.com/marcosnils/bin"

    platforms = LINUX_LIKE, MACOS, WINDOWS

    requirement = ">=0.27.0"
    """The release whose listing layout {meth}`installed` reproduces: it reserves
    a leading column of the version field for the pin marker. The parser tolerates
    the older unreserved layout too, but the floor tracks what is verified.
    """

    extra_env: ClassVar = {
        # bin colors on its own initiative whenever `CI` is non-empty. This keeps
        # the stdout table clean; the stderr report is stripped separately, that
        # stream's styling being beyond this lever's reach.
        "NO_COLOR": "1",
    }

    version_regexes = (r"^bin version (?P<version>\S+)",)
    r"""Search the version on the first line.

    ```{code-block} shell-session

    $ bin --version
    bin version 0.29.1
    commit: c24db4aced89c855062fe8e2907ae0deb3fb9f53
    built at: 2026-08-02T13:37:10Z
    built by: goreleaser
    ```

    Four lines are printed and the version is the third word of the first, bare
    and without a `v`. There is no `version` subcommand.
    """

    _INSTALLED_REGEXP = re.compile(
        r"^(?P<package_id>\S.*?)\s{2,}\*?(?P<installed_version>\S+)\s{2,}\S+\s{2,}"
        r"(?:OK|missing .*)$",
    )
    """One row of the installed table.

    A four-column table padded with at least two spaces between cells, each column
    as wide as its widest value, so no column sits at a fixed offset and the
    separator is the only thing worth anchoring on. Three details drive the
    pattern. The first column is a path and may itself contain a single space, so
    it is matched lazily up to the first run of two. The version is preceded by a
    reserved column carrying `*` when the binary is pinned, which the optional
    marker consumes so it never lands in the version. And the status column is
    either `OK` or `missing <path>`, the latter carrying spaces of its own, so the
    pattern is anchored on it at the end rather than counting fields. A row whose
    version or URL is empty collapses to three columns and correctly fails to
    match, rather than silently shifting a URL into the version field.
    """

    _OUTDATED_REGEXP = re.compile(
        r"^\s*•\s+(?P<package_id>.+?)\s+(?P<installed_version>\S+)\s+->\s+"
        r"(?P<latest_version>\S+)\s+\(\S+\)$",
    )
    """One upgradable binary of the dry-run report.

    Bulleted rather than tabulated, since this is a log stream rather than a
    table. The path is matched lazily and the versions are anchored on the arrow
    between them, so a path carrying a space is read correctly instead of shifting
    a fragment into the installed version. The run's closing `command failed` line
    carries no arrow and is skipped by not matching.
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        ```{code-block} shell-session

        $ bin list
        /home/user/.local/bin/fzf         v0.74.2  github.com/junegunn/fzf                                    OK
        /home/user/.local/bin/rg          14.1.1   https://github.com/BurntSushi/ripgrep/releases/tag/14.1.1  OK
        /home/user/.local/bin/terraform  *1.5.7    releases.hashicorp.com/terraform                           OK
        ```
        """
        output = self.run_cli("list")
        yield from self.parse_regex_lines(self._INSTALLED_REGEXP, output)

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        This is the operation that keeps bin a class rather than a definition, on
        two counts a fixed argument list cannot express.

        ```{important}
        The report is written to `stderr` while `stdout` stays empty, and the run
        exits `3` when it finds anything to update. Both are deliberate on bin's
        side: `0` means everything is current, so a zero exit is the *empty*
        answer here and only a code that is neither means the check itself
        failed. The entries the failing exit records are discarded, since this one
        is a result rather than an error.
        ```

        ```{code-block} shell-session

        $ bin update --dry-run
        ```

        ```{code-block} console

          • /home/user/.local/bin/fzf v0.40.0 -> v0.74.2 (https://github.com/junegunn/fzf/releases/tag/v0.74.2)
          • /home/user/.local/bin/gh v2.40.0 -> v2.97.0 (https://github.com/cli/cli/releases/tag/v2.97.0)
          ⨯ command failed                                   error=Updates found, exit (dry-run mode).
        ```

        ```{note}
        A pinned binary is reported as pinned and skipped before its version is
        ever checked, so it never appears here. That matches the listing, which
        marks it with a `*`.
        ```
        """
        before = len(self.cli_errors)
        self.run_cli("update", "--dry-run")

        last = self._last_run
        if last is None:
            return
        code, _stdout, stderr = last
        if code not in (0, DRY_RUN_UPDATES_FOUND):
            return
        # The dry run reports through its exit code, so the entry a non-zero one
        # recorded is not a failure to carry into mpm's own error tally.
        del self.cli_errors[before:]

        yield from self.parse_regex_lines(
            self._OUTDATED_REGEXP,
            _ANSI_REGEXP.sub("", stderr),
        )

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        `--yes` answers the single batch confirmation `update` asks before
        applying, and `--continue-on-error` keeps one failing binary from
        abandoning the rest of the run.

        ```{code-block} shell-session

        $ bin update --yes --continue-on-error
        ```
        """
        return self.build_cli("update", "--yes", "--continue-on-error")

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the package provided as parameter.

        Unlike some whole-system upgraders, naming a binary genuinely restricts
        the run to it.

        ```{code-block} shell-session

        $ bin update --yes --continue-on-error /home/user/.local/bin/fzf
        ```
        """
        return self.build_cli("update", "--yes", "--continue-on-error", package_id)

    def remove(self, package_id: str) -> str:
        """Removes a package.

        ```{warning}
        `remove` reports a name it could not resolve on `stderr` and still exits
        `0`, so a zero exit here means the command ran, not that anything was
        removed. Confirm a removal by listing again.
        ```

        ```{code-block} shell-session

        $ bin remove /home/user/.local/bin/fzf
        ```
        """
        return self.run_cli("remove", package_id)
