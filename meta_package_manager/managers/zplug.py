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

import os
import re
import shlex
from pathlib import Path
from typing import ClassVar

from click_extra.execution import args_cleanup
from extra_platforms import LINUX_LIKE, MACOS

from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


def zplug_source_path() -> Path:
    """Locate the `init.zsh` file every invocation sources.

    zplug installs itself into `$ZPLUG_HOME`, falling back to `~/.zplug` when
    the variable is unset, exactly as its own installer and documentation do.
    The path is returned whether or not it exists, so the built command stays
    well-formed and simply fails to source, which is what makes the version
    probe double as zplug's presence check.
    """
    home = os.environ.get("ZPLUG_HOME") or str(Path.home() / ".zplug")
    return Path(home) / "init.zsh"


class Zplug(PackageManager):
    """zplug is a plugin manager for Zsh.

    Plugins are declared in the user's `.zshrc` with `zplug "user/repo"` calls,
    then materialized under `$ZPLUG_HOME/repos`. Packages are identified by the
    `user/repo` slug zplug reports, which is the id mpm keys them on.

    ```{caution}
    `zplug` is a shell function, not a standalone binary: it is defined by
    sourcing `$ZPLUG_HOME/init.zsh`, so it cannot serve as the manager's CLI.
    Every invocation is therefore wrapped in `zsh -c`. Zsh is the binary mpm
    executes, and zplug's own presence is established by the version probe: a
    host with Zsh but no zplug fails to source and reports no version, which
    leaves the manager unavailable.
    ```

    ```{caution}
    No `install` and no `remove`: zplug materializes exactly the plugin set the
    user's own `.zshrc` declares. `zplug install` clones what that file already
    names and `zplug clean` drops repositories it no longer names, so neither
    takes a plugin of mpm's choosing. Installing one would mean mpm editing the
    user's `.zshrc`, which is configuration mpm does not own. Both operations
    are therefore not implemented rather than faked, and mpm auto-skips them.
    ```

    ```{note}
    No `outdated`: `zplug status` does check each plugin against its remote,
    but it reports through a progress display rather than a parseable list, and
    its output is not pinned by any upstream sample this implementation could
    be held to. `upgrade --all` still works and mpm auto-skips the operation.
    ```

    Documentation: [zplug](https://github.com/zplug/zplug).
    """

    name = "Zsh zplug"

    homepage_url = "https://github.com/zplug/zplug"
    logo = "zsh"

    platforms = LINUX_LIKE, MACOS

    requirement = ">=2.0.0"
    """The `2.x` series is where the command set this class drives settled.

    `zplug list` and the bare `zplug update` both date from the `2.0`
    rewrite that introduced `$ZPLUG_HOME` and the `init.zsh` entry point this
    manager sources.
    """

    cli_names = ("zsh",)
    """Zsh is the binary mpm actually executes.

    zplug is a shell function defined by an `init.zsh` file that is sourced,
    never executed, so it cannot serve as the manager's CLI: mpm requires an
    executable. Keying the manager on Zsh instead makes the version probe the
    presence check.
    """

    extra_env: ClassVar = {
        "NO_COLOR": "1",
        "SHELL_SESSIONS_DISABLE": "1",
    }
    """`NO_COLOR` keeps zplug's status glyphs out of the listing so the parser
    sees clean text. `SHELL_SESSIONS_DISABLE` keeps macOS' Zsh session
    bookkeeping from writing a session file on every query, as for
    {class}`~meta_package_manager.managers.antidote.Antidote`.
    """

    version_regexes = (r"(?P<version>\d+(?:\.\d+)+)",)
    """zplug prints its version bare, with no name or prefix around it.

    Its `--version` handler is a single
    `__zplug::io::print::put "$_ZPLUG_VERSION\\n"`, so the regex is anchored on
    the shape of the version itself rather than on a surrounding label.

    ```{code-block} shell-session

    $ zsh -c 'source ~/.zplug/init.zsh && zplug --version'
    2.4.2
    ```
    """

    _INSTALLED_REGEXP = re.compile(r"^(?P<package_id>\S+)\s+=>")
    """The left-hand side of each `<package> => <tags>` row.

    zplug reports no version: a plugin is a Git clone tracking a branch, and
    the right-hand side holds its `as:`/`from:`/`use:` tags (or `nil` when it
    has none), never a revision.
    """

    def build_cli(self, *args, **kwargs) -> tuple[str, ...]:
        """Wrap all CLI invocations in the Zsh shell zplug needs.

        The version probe is guarded by a readability test that exits
        successfully when `init.zsh` is absent. Zsh is the default shell on
        macOS and near ubiquitous elsewhere, so an unguarded probe would turn
        every host that merely has Zsh into a manager reporting errors. An
        `init.zsh` that is present but broken still fails loudly.

        ```{note}
        The `**kwargs` accepted by the base class (`auto_pre_args`, `sudo`,
        etc.) are accepted but ignored because every invocation goes through
        the `zsh -c` wrapper and zplug never requires elevated privileges.
        ```
        """
        clean_args = args_cleanup(*args)
        zplug_cmd = " ".join(shlex.quote(arg) for arg in clean_args)
        source_path = shlex.quote(str(zplug_source_path()))

        if clean_args[:1] == ("--version",):
            probe = (
                f"[[ -r {source_path} ]] || exit 0; "
                f"source {source_path} && zplug --version"
            )
            return ("zsh", "-c", probe)

        return ("zsh", "-c", f"source {source_path} && zplug {zplug_cmd}")

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        zplug prints one plugin per line as `<package> => <tags>`, the tags
        being the `as:`, `from:`, `use:` and `frozen:` annotations declared for
        it, or the literal `nil` when it carries none. Only the left-hand side
        is an identifier, and no version is reported anywhere: a plugin is a
        Git clone tracking a branch.

        A plugin sourced from a local directory is listed by its absolute path
        instead, and is yielded under that path as its id.

        ```{code-block} shell-session

        $ zsh -c 'source ~/.zplug/init.zsh && zplug list'
        zplug/zplug => nil
        b4b4r07/zsh-gomi => as:command, use:bin/gomi
        peco/peco => as:command, from:gh-r, frozen:1
        ```
        """
        output = self.run_cli("list")
        yield from self.parse_regex_lines(self._INSTALLED_REGEXP, output)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        A bare `zplug update` re-reads the plugin set the user's `.zshrc`
        declares and pulls each one.

        ```{code-block} shell-session

        $ zplug update
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

        $ zplug update b4b4r07/zsh-gomi
        ```
        """
        return self.build_cli("update", package_id)
