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

from extra_platforms import LINUX_LIKE, MACOS, WINDOWS

from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class Volta(PackageManager):
    """Volta manages JavaScript command-line tools, installing each package from
    the npm registry into its own isolated image pinned to a specific Node
    runtime.

    Tools installed with `volta install` never land in npm's global prefix:
    Volta keeps them under its own `VOLTA_HOME` layout and exposes their
    binaries through shims on `PATH`. The `npm` executable found on a
    Volta-equipped host is itself such a shim, and `npm --global` operations do
    not see Volta-managed tools, hence this dedicated backend (requested in
    [#1995](https://github.com/kdeldycke/meta-package-manager/issues/1995)).

    Volta has no command listing outdated packages, so `outdated` (and with it
    the synthesized `upgrade --all`) is unsupported: upgrades are targeted, by
    reinstalling the latest release of a named package.
    """

    unmaintained = True

    unmaintained_message = (
        "Volta's maintainers [declared the project unmaintained on 2025-11-14]"
        "(https://github.com/volta-cli/volta/issues/2080) and recommend migrating "
        "to [`mise`](https://mise.jdx.dev). The final release, [`2.0.2`]"
        "(https://github.com/volta-cli/volta/releases/tag/v2.0.2), dates back to "
        "2024-12-05."
    )

    homepage_url = "https://volta.sh"

    platforms = LINUX_LIKE, MACOS, WINDOWS

    requirement = ">=1.0.2"
    """[`1.0.2`](https://github.com/volta-cli/volta/blob/main/RELEASES.md#version-102)
    ships the fixes making `volta list` report correct information
    ([volta-cli/volta#778](https://github.com/volta-cli/volta/issues/778) and
    [volta-cli/volta#926](https://github.com/volta-cli/volta/issues/926)), the
    listing this backend parses. The plain output format itself is stable from
    `1.0` through the final `2.0.2` release.
    """

    cli_search_path = ("~/.volta/bin",)
    """`VOLTA_HOME/bin`, where the official install script places the `volta`
    binary on Linux and macOS. Windows installers register the binary on `PATH`
    themselves.
    """

    _LIST_REGEXP = re.compile(
        r"^package (?P<package_id>\S+)@(?P<installed_version>\S+) /.* \(default\)$",
    )
    """Retains only the `package <name>@<version> / <binaries> / <platform>`
    lines flagged `(default)`, skipping the `runtime` and `package-manager`
    lines. The greedy `package_id` group backtracks to the last `@` of the
    spec, so scoped names (`@scope/name@1.0.0`) split correctly.
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        `volta list all --format plain` prints one line per tool. Only
        `package` lines carrying the `(default)` marker are retained: they are
        the globally-installed npm packages Volta manages through
        `volta install` and `volta uninstall`. `runtime` (Node) and
        `package-manager` (npm, pnpm, Yarn) lines are pinned toolchain
        components Volta cannot uninstall, so they are kept out of the
        inventory. So is a package shadowed by the working directory's own
        JavaScript project: it renders with `project` placeholders instead of
        versions, so run `mpm` outside a project tree for the full global
        inventory.

        The sample below is derived from the format's [unit tests in Volta's
        `plain.rs`](https://github.com/volta-cli/volta/blob/v2.0.2/src/command/list/plain.rs)
        and the trace of
        [#1995](https://github.com/kdeldycke/meta-package-manager/issues/1995):

        ```{code-block} shell-session

        $ volta list all --format plain
        runtime node@12.4.0 (default)
        package-manager npm@6.13.4 (default)
        package-manager yarn@1.16.0 (default)
        package @larksuite/cli@1.0.79 / lark-cli / node@12.4.0 npm@built-in (default)
        package ember-cli@3.10.0 / ember / node@12.4.0 npm@built-in (default)
        package typescript@3.4.1 / tsc, tsserver / node@12.4.0 npm@built-in (default)
        ```
        """
        output = self.run_cli("list", "all", "--format", "plain", must_succeed=True)
        yield from self.parse_regex_lines(self._LIST_REGEXP, output)

    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        Volta pins exact versions natively through npm's `name@version` spec
        syntax; a bare name resolves to the latest release.

        ```{code-block} shell-session

        $ volta install typescript@3.4.1
        ```
        """
        spec = f"{package_id}@{version}" if version else package_id
        return self.run_cli("install", spec)

    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the package provided as parameter.

        Volta has no dedicated upgrade command for packages: reinstalling a
        bare name fetches the latest release and swaps it in as the new
        default.

        ```{code-block} shell-session

        $ volta install ember-cli
        ```
        """
        spec = f"{package_id}@{version}" if version else package_id
        return self.build_cli("install", spec)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        ```{code-block} shell-session

        $ volta uninstall ember-cli
        ```
        """
        return self.run_cli("uninstall", package_id)
