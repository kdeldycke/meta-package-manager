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

from ..capabilities import search_capabilities, version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class Pkgit(PackageManager):
    """pkgit, which compiles and installs packages straight from git repositories.

    A package is a git repository the user declares in `~/.config/pkgit/init.lua`,
    which pkgit clones and builds through the repository's own `bldit.lua`
    recipe. That configuration is the registry: pkgit reaches no catalog of its
    own and fronts no other package manager, so it is wrapped on its own terms
    rather than declined as a translation layer.

    ```{note}
    The configuration is mandatory, and its absence is what makes an
    unconfigured pkgit correctly undetectable: every subcommand, `--version`
    included, exits `1` with `cannot run configuration script`, so the version
    probe finds nothing and mpm reports the manager unavailable until
    `make defconfig` has run.
    ```

    ```{caution}
    `remove` is deliberately absent. `pkgit --remove <package>` aborts on a
    package declared in `init.lua`, with `'repositories' is not a table.`
    followed by `PANIC: unprotected error in call to Lua API (attempt to index
    a nil value)`, exiting `1` and leaving the package installed. It succeeds
    only on a repository pulled in as a build dependency, and even then leaves
    the checkout behind so {meth}`installed` keeps reporting it.
    ```

    ```{note}
    A listing carries no version. pkgit enumerates the directories under its
    share tree, one per cloned repository, and a package is whatever `HEAD`
    currently points at, so there is nothing to report as an installed version.
    Build dependencies are cloned as packages too and appear alongside what was
    asked for.
    ```

    Documentation: [pkgit README](https://git.symlinx.net/pkgit/about/).
    """

    name = "pkgit"

    homepage_url = "https://git.symlinx.net/pkgit"

    platforms = LINUX_LIKE
    """`src/files.c` opens with `O_NOFOLLOW` behind no feature-test macro, which
    is why the build fails on macOS and the claim stops at Linux.
    """

    requirement = ">=1.2.0"
    """The release carrying both the verb set driven here and the listing shape
    parsed below: `src/list_pkgs.c` already prints one bare name per line there.

    The floor cannot be tighter than that even where it should be. pkgit has not
    bumped `VERSION` since the tag, so the 58 commits on top of it report
    `1.2.0` too, and no version string separates the two.
    """

    _INSTALLED_REGEXP = re.compile(r"^(?P<package_id>\S+)$")

    version_regexes = (r"(?P<version>\d+\S*)",)
    """
    ```{code-block} shell-session

    $ pkgit --version
    1.2.0
    ```
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        ```{note}
        An empty listing is the honest answer on a machine that has installed
        nothing: pkgit exits `0` with `could not open <share tree>` on
        `<stderr>` before the directory exists, and reports no package, which is
        the same thing.
        ```

        ```{code-block} shell-session

        $ pkgit --list
        git
        pkgit
        luajit.git
        ```
        """
        output = self.run_cli("--list")
        yield from self.parse_regex_lines(self._INSTALLED_REGEXP, output)

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        Only the repositories the configuration declares are searched, and the
        result is a bare name, so mpm's own refiltering narrows whatever comes
        back.

        ```{caution}
        Search does not support extended or exact matching.
        ```

        ```{code-block} shell-session

        $ pkgit --search pkgit
        pkgit
        ```
        """
        output = self.run_cli("--search", query)
        yield from self.parse_regex_lines(self._INSTALLED_REGEXP, output)

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package, compiling it from its repository.

        ```{code-block} shell-session

        $ pkgit --install pkgit
        ```
        """
        return self.run_cli("--install", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all installed packages.

        ```{caution}
        pkgit exits `0` whether or not a repository updated, reporting each
        outcome on `<stderr>` instead, so a failed update cannot be told from a
        successful one by exit code alone.
        ```

        ```{code-block} shell-session

        $ pkgit --update
        ```
        """
        return self.build_cli("--update")
