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
from functools import cached_property

from extra_platforms import LINUX_LIKE

from ..capabilities import search_capabilities, version_not_implemented
from ..execution import VERSION_PROBE
from ..manager import PackageManager
from ..version import parse_version

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package
    from ..version import TokenizedString


class Lure(PackageManager):
    """LURE, the Linux User REpository: an AUR-shaped build system for any distro.

    A package is a build recipe in a git repository LURE clones, and the
    resulting artifact is handed to the host's own package manager, so LURE
    reaches packages no distro archive carries while leaving the installed state
    with `apt`, `dnf`, `pacman` or whichever backend the host runs.

    ```{important}
    LURE escalates itself and refuses to be escalated. It aborts as root with
    *"Running LURE as root is forbidden as it may cause catastrophic damage to
    your system"*, and calls its own configured `RootCmd` (`sudo` by default)
    for the privileged half. mpm therefore marks nothing here privileged, the
    same treatment [`chromebrew`](chromebrew.md) gets.
    ```

    ```{caution}
    `remove` and `upgrade` are absent, and the reason is one field. LURE's
    default backend options set `NoConfirm: false`, and only its build path
    flips it true, so an install reaches the backend as `apt install -y` while a
    removal reaches it as a bare `apt remove` and blocks forever on a
    confirmation prompt no mpm run can answer. `--pm-args` can push a flag
    through, but the right flag is the backend's own: `-y` suits apt, dnf and
    zypper, while pacman reads `-y` as *refresh the databases*, so there is no
    value mpm could pass without knowing a backend it cannot resolve.
    ```

    ```{note}
    Every subcommand pulls its repositories before doing anything else, so even
    a listing costs a network round-trip and prints the git progress on
    `<stderr>`. Only the packages themselves reach `<stdout>`.
    ```

    Documentation: [LURE readme](https://github.com/lure-sh/lure).
    """

    maintenance_note: str | None = (
        "LURE's own forge at `git.elara.ws` answers `502` and `lure.sh` answers "
        "`404` behind a placeholder certificate, so its installer and release "
        "binaries are both unreachable and the tool has to be built from source. "
        "Its author announced a pause rather than an end in "
        "[lure-sh/lure#89](https://github.com/lure-sh/lure/issues/89) on "
        "2025-05-04, *\"I intend to start working on it again as soon as I'm in a "
        'stable position again"*, and the recipe repository this manager reads '
        "is on GitHub and still moving."
    )

    name = "LURE"

    homepage_url = "https://github.com/lure-sh/lure"

    platforms = LINUX_LIKE

    requirement = ">=0.1.3"
    """The newest release, and the one this parser was checked against: `list.go`
    already carries the `installed` flag there.

    The build driven here is that tag plus a single commit touching the install
    script, LURE having tagged nothing since.
    """

    cli_names = ("lure",)

    _LIST_REGEXP = re.compile(
        r"^[^/\s]+/(?P<package_id>\S+)\s+(?P<version>\S+)$",
    )
    """A row is `<repo>/<name> <version>`.

    The repository is matched but dropped: `lure install` takes the bare name,
    so that is what a package ID has to be for mpm to hand one back. Two
    repositories shipping the same name would collapse onto one entry, which in
    practice is a single `default` repository.
    """

    version_cli_options = ("version",)
    """`lure --version` is rejected as `flag provided but not defined`, the
    version living behind a subcommand instead.
    """

    version_regexes = (r"v?(?P<version>\d+\.\d+\.\d+)",)
    """
    ```{code-block} shell-session

    $ lure version
    v0.1.3
    ```
    """

    @cached_property
    def version(self) -> TokenizedString | None:
        """Parse the version off `<stderr>`, where LURE alone prints it.

        `lure version` reaches Go's builtin `println`, which writes to
        `<stderr>` and leaves `<stdout>` empty, so the inherited probe (reading
        the return value of
        {meth}`~meta_package_manager.execution.CLIExecutor.run_cli`) would find
        nothing and leave the manager permanently unavailable.

        Both streams are searched, not `<stderr>` alone: a version that moved to
        `<stdout>` should not take the manager offline.
        """
        if not self.executable:
            return None

        self._active_operation = VERSION_PROBE
        output = self.run_cli(
            self.version_cli_options,
            auto_pre_cmds=False,
            auto_pre_args=False,
            auto_post_args=False,
            force_exec=True,
        )

        error = self._last_run[2] if self._last_run else ""
        haystack = "\n".join(stream for stream in (output, error) if stream)

        for regex in self.version_regexes:
            match = re.compile(regex, re.MULTILINE).search(haystack)
            if match:
                version_string = match.groupdict().get("version")
                if version_string:
                    return parse_version(version_string)
        return None

    def _parse_rows(self, output: str) -> Iterator[tuple[str, str]]:
        """Yield `(package_id, version)` per row of a `list` output.

        The two listings share one row shape but not one meaning, the version
        being the installed one under `--installed` and the available one
        otherwise, so the rows are read here and labelled by each caller rather
        than through
        {meth}`~meta_package_manager.manager.PackageManager.parse_regex_lines`.
        """
        for line in output.splitlines():
            match = self._LIST_REGEXP.match(line)
            if match:
                yield match.group("package_id"), match.group("version")

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        The version is the built artifact's, carrying the recipe's release
        number, where {meth}`search` reports the recipe's own.

        ```{code-block} shell-session

        $ lure list --installed
        default/neofetch 7.1.0-1
        ```
        """
        output = self.run_cli("list", "--installed")
        for package_id, version in self._parse_rows(output):
            yield self.package(id=package_id, installed_version=version)

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        LURE has no search verb: `list` prints the whole catalog of every
        repository it tracks, and mpm's own refiltering narrows it.

        ```{caution}
        Search does not support extended or exact matching, and the query never
        reaches LURE.
        ```

        ```{code-block} shell-session

        $ lure list
        default/admc 0.13.0-alt1
        default/admc-git 3592.023670c
        default/binutils-z80 2.43
        default/cava 0.9.1
        default/cava-git 0
        default/deduplicator 0.1.6
        ```
        """
        output = self.run_cli("list")
        for package_id, version in self._parse_rows(output):
            yield self.package(id=package_id, latest_version=version)

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package, building it from its recipe.

        This is the one path LURE runs non-interactively on its own: the build
        sets `NoConfirm`, so the backend is handed its own confirmation flag.

        ```{code-block} shell-session

        $ lure install neofetch
        ```
        """
        return self.run_cli("install", package_id)

    def sync(self) -> None:
        """Pull every tracked recipe repository.

        ```{code-block} shell-session

        $ lure refresh
        ```
        """
        self.run_cli("refresh")
