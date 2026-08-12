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

from extra_platforms import LINUX_LIKE, MACOS

from ..manager import PackageManager


class Sheldon(PackageManager):
    """Sheldon is a fast, configurable plugin manager for any shell.

    Plugins are declared in a `plugins.toml` config file, each under a unique
    local name, and materialized into a `plugins.lock` file that Sheldon
    generates. Packages are identified by that local name, which is what every
    command below takes.

    Unlike the other shell plugin managers mpm wraps, Sheldon is a real
    compiled binary rather than a sourced shell function, so it needs no
    interpreter wrapper: mpm calls `sheldon` directly.

    ```{caution}
    No `installed`: Sheldon ships no command that prints its plugins. The
    inventory does exist, in the `plugins.toml` config file, but reaching it
    would mean mpm reading and parsing a configuration file instead of calling
    a CLI, which is not how a manager gathers packages here. The upstream
    command set is `init`, `add`, `edit`, `remove`, `lock`, `source`,
    `completions` and `version`: none of them lists anything.
    ```

    ```{caution}
    No `install`: `sheldon add` requires *two* values, a unique local name and
    a source flag naming where the plugin comes from (`--github`, `--git`,
    `--gist`, `--remote` or `--local`). mpm's install carries a single package
    id, which cannot supply both, and guessing a source from the id would be
    inventing a mapping Sheldon never defined. The operation is therefore not
    implemented rather than faked, and mpm auto-skips it.
    ```

    ```{note}
    No `outdated`: Sheldon compares nothing against its remotes short of
    performing the update. `upgrade --all` still works, and mpm auto-skips the
    operation.
    ```

    Documentation: [sheldon](https://sheldon.cli.rs).
    """

    name = "Sheldon"

    homepage_url = "https://sheldon.cli.rs"

    platforms = LINUX_LIKE, MACOS

    requirement = ">=0.6.0"
    """The series carrying the subcommand set this class drives.

    `0.6.0` is where `lock --update` settled as the way to refresh every plugin
    source, split from the `source` command that generates the shell script.
    """

    extra_env: ClassVar = {"NO_COLOR": "1"}
    """Sheldon colors its progress output, which `NO_COLOR` disables. It also
    honors a `--color` flag, but the environment variable covers every
    invocation without threading a flag through each one.
    """

    version_regexes = (r"sheldon\s+(?P<version>\S+)",)
    """
    Sheldon declares its version through clap, which prints the crate name and
    release. The separate `sheldon version` subcommand prints a longer report,
    and is not what the probe reads.

    ```{code-block} shell-session

    $ sheldon --version
    sheldon 0.8.2
    ```
    """

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        `lock --update` re-fetches every plugin source declared in
        `plugins.toml` and regenerates the lock file. The sibling `--reinstall`
        discards and re-clones each source instead, which is a repair rather
        than an upgrade, so it is not what this builds.

        ```{code-block} shell-session

        $ sheldon lock --update
        ```
        """
        return self.build_cli("lock", "--update")

    def remove(self, package_id: str) -> str:
        """Remove one package.

        `remove` takes the plugin's unique local name, the same identifier
        `add` assigned it in `plugins.toml`, and drops its entry from that
        file.

        ```{code-block} shell-session

        $ sheldon remove zsh-autosuggestions
        ```
        """
        return self.run_cli("remove", package_id)
