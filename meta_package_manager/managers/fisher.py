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

import shlex
from typing import ClassVar

from click_extra.execution import args_cleanup
from extra_platforms import LINUX_LIKE, MACOS

from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class Fisher(PackageManager):
    """Fisher is a plugin manager for the Fish shell.

    Fisher clones each plugin from GitHub or any other forge into
    `$fisher_path`, and records the set in the user's `fish_plugins` file.
    Plugins are identified by the lower-cased `owner/repo` slug Fisher both
    reports and accepts, which is the id mpm keys them on. A plugin may carry
    an `@ref` suffix pinning it to a Git tag or branch, and that suffix is what
    mpm surfaces as the installed version.

    ```{caution}
    `fisher` is a Fish function, not a standalone binary: it ships as a
    `functions/fisher.fish` file that Fish autoloads, so it cannot serve as the
    manager's CLI. Every invocation is therefore wrapped in `fish -c`. Fish is
    the binary mpm executes, and Fisher's own presence is established by the
    version probe: a host with Fish but no Fisher autoloads nothing, reports no
    version, and leaves the manager unavailable.
    ```

    ```{note}
    No `outdated`: Fisher exposes no dry run and no upstream comparison. It
    tracks a branch rather than a release, so "behind" is not a question it
    answers. `upgrade --all` still works, and mpm auto-skips the operation.
    ```

    ```{note}
    No `search`: Fisher resolves plugins straight from forge URLs and indexes
    no registry to search.
    ```

    Documentation: [fisher](https://github.com/jorgebucaran/fisher).
    """

    name = "Fish fisher"

    homepage_url = "https://github.com/jorgebucaran/fisher"

    platforms = LINUX_LIKE, MACOS

    requirement = ">=4.0.0"
    """The `4.x` rewrite is where this CLI settled.

    `4.0.0` is the release that introduced the `$_fisher_plugins` inventory
    `list` prints, the `fish_plugins` file `install` and `remove` maintain, and
    the plugin-scoped `update` this class builds. Fisher `3.x` had a different
    command set entirely, keyed on a `fishfile`.
    """

    cli_names = ("fish",)
    """Fish is the binary mpm actually executes.

    Fisher is a shell function that Fish autoloads from its functions path, and
    is never executed as a program, so it cannot be the manager's CLI: mpm
    requires an executable. Keying the manager on Fish instead makes the
    version probe the presence check.
    """

    extra_env: ClassVar = {"NO_COLOR": "1"}
    """Fisher prints its progress through Fish's own coloring, which
    `NO_COLOR` disables so the listing parses as clean text.
    """

    version_regexes = (r"fisher, version (?P<version>\S+)",)
    """
    ```{code-block} shell-session

    $ fish -c 'functions --query fisher; or exit 0; fisher --version'
    fisher, version 4.4.8
    ```
    """

    def build_cli(self, *args, **kwargs) -> tuple[str, ...]:
        """Wrap all CLI invocations in the Fish shell Fisher needs.

        The version probe is guarded by `functions --query`, which exits
        successfully when Fisher is not on the functions path. Fish is a
        general-purpose shell, so an unguarded probe would turn every host that
        merely has Fish into a manager reporting errors. A Fisher that is
        present but broken still fails loudly.

        ```{note}
        The `**kwargs` accepted by the base class (`auto_pre_args`, `sudo`,
        etc.) are accepted but ignored because every invocation goes through
        the `fish -c` wrapper and Fisher never requires elevated privileges.
        ```
        """
        clean_args = args_cleanup(*args)
        fisher_cmd = " ".join(shlex.quote(arg) for arg in clean_args)

        if clean_args[:1] == ("--version",):
            probe = "functions --query fisher; or exit 0; fisher --version"
            return ("fish", "-c", probe)

        return ("fish", "-c", f"fisher {fisher_cmd}")

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        Fisher prints one plugin per line, exactly as recorded: the lower-cased
        `owner/repo` slug, optionally suffixed with the `@ref` it was pinned to.
        A plugin installed from a local directory is listed by its absolute
        path instead, and is yielded under that path as its id.

        The `@ref` is a Git tag or branch, which is the only revision Fisher
        records: an unpinned plugin tracks its default branch and so reports no
        version at all.

        ```{code-block} shell-session

        $ fish -c 'fisher list'
        jorgebucaran/fisher
        ilancosman/tide@v5
        jorgebucaran/nvm.fish
        ```
        """
        output = self.run_cli("list")
        for line in output.splitlines():
            plugin = line.strip()
            if not plugin:
                continue
            # Only the ref suffix is split off: a bare slug or a local path
            # carries no "@" and yields no version.
            package_id, _, ref = plugin.partition("@")
            yield self.package(id=package_id, installed_version=ref or None)

    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        `install` both clones the plugin and appends it to the user's
        `fish_plugins` file, so a package installed through mpm is loaded by
        the next shell instead of sitting on disk unreferenced.

        A `version` is passed straight through as Fisher's `@ref` suffix. That
        round-trips exactly: the ref {meth}`installed` reports is the one
        Fisher accepts back here.

        ```{code-block} shell-session

        $ fish -c 'fisher install ilancosman/tide@v5'
        fisher installing ilancosman/tide@v5
                 Fetching https://codeload.github.com/ilancosman/tide/tar.gz/v5
                 Installing ilancosman/tide@v5
                 12 functions, 2 completions, 3 conf.d scripts
        ```
        """
        return self.run_cli(
            "install", f"{package_id}@{version}" if version else package_id
        )

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        A bare `fisher update` re-reads the user's `fish_plugins` file and
        updates every plugin listed in it.

        ```{code-block} shell-session

        $ fish -c 'fisher update'
        ```
        """
        return self.build_cli("update")

    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade one package.

        ```{code-block} shell-session

        $ fish -c 'fisher update jorgebucaran/nvm.fish'
        ```
        """
        return self.build_cli(
            "update",
            f"{package_id}@{version}" if version else package_id,
        )

    def remove(self, package_id: str) -> str:
        """Remove one package.

        `remove` is the exact counterpart of {meth}`Fisher.install`: it drops
        the plugin's files and its line from the user's `fish_plugins` file, so
        the next shell no longer loads it.

        ```{code-block} shell-session

        $ fish -c 'fisher remove jorgebucaran/nvm.fish'
        fisher removing jorgebucaran/nvm.fish
                 5 functions, 1 completion, 1 conf.d script
        ```
        """
        return self.run_cli("remove", package_id)
