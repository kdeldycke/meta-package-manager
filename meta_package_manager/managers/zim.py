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


_ABSENT_FLAGS = frozenset({"not installed", "unused"})
"""Parenthesized flags marking a row that is not an installed module.

`not installed` is a module the user's `.zimrc` declares but that was never
fetched, and `unused` is a leftover directory no longer declared. Neither is
part of the inventory, while `external`, `frozen` and `disabled` all still are.
"""


def zim_source_path() -> Path:
    """Locate the `init.zsh` file every invocation sources.

    Zim installs itself into `$ZIM_HOME`, falling back to
    `${ZDOTDIR:-${HOME}}/.zim` when the variable is unset, exactly as its own
    installer and `zimfw.zsh` do. The path is returned whether or not it
    exists, so the built command stays well-formed and simply fails to source,
    which is what makes the version probe double as Zim's presence check.
    """
    zim_home = os.environ.get("ZIM_HOME")
    if not zim_home:
        base = os.environ.get("ZDOTDIR") or str(Path.home())
        zim_home = str(Path(base) / ".zim")
    return Path(zim_home) / "init.zsh"


class Zim(PackageManager):
    """Zim is a configuration framework and module manager for Zsh.

    Modules are declared in the user's `.zimrc`, then cloned under `$ZIM_HOME`.
    Packages are identified by the module name Zim reports, which is the id mpm
    keys them on.

    ```{caution}
    `zimfw` is a shell function, not a standalone binary: it is defined by
    sourcing `$ZIM_HOME/init.zsh`, and the `zimfw.zsh` script behind it carries
    no shebang. Every invocation is therefore wrapped in `zsh -c`. Zsh is the
    binary mpm executes, and Zim's own presence is established by the version
    probe: a host with Zsh but no Zim fails to source and reports no version,
    which leaves the manager unavailable.
    ```

    ```{caution}
    No `install` and no `remove`: Zim materializes exactly the module set the
    user's own `.zimrc` declares. `zimfw install` fetches what that file
    already names and `zimfw uninstall` drops what it no longer names, so
    neither takes a module of mpm's choosing. Installing one would mean mpm
    editing the user's `.zimrc`, which is configuration mpm does not own. Both
    operations are therefore not implemented rather than faked, and mpm
    auto-skips them.
    ```

    ```{note}
    No `outdated`: `zimfw check` does compare each module against its remote,
    but it reports through the same progress display as `update` rather than a
    parseable list, and no upstream sample pins its format down. `upgrade
    --all` still works and mpm auto-skips the operation.
    ```

    Documentation: [zimfw](https://zimfw.sh).
    """

    name = "Zsh Zim"

    homepage_url = "https://zimfw.sh"
    logo = "zsh"

    platforms = LINUX_LIKE, MACOS

    requirement = ">=1.0.0"
    """Zim versions independently of Zsh, so no Zsh floor applies here.

    The `1.x` series is where `zimfw` became the single entry point carrying
    the `list`, `update` and `version` subcommands this class drives.
    """

    cli_names = ("zsh",)
    """Zsh is the binary mpm actually executes.

    Zim is a shell function defined by an `init.zsh` file that is sourced,
    never executed, so it cannot serve as the manager's CLI: mpm requires an
    executable. Keying the manager on Zsh instead makes the version probe the
    presence check.
    """

    extra_env: ClassVar = {
        "NO_COLOR": "1",
        "SHELL_SESSIONS_DISABLE": "1",
    }
    """`NO_COLOR` drops the bold Zim wraps every module name in, so the listing
    parses as clean text. `SHELL_SESSIONS_DISABLE` keeps macOS' Zsh session
    bookkeeping from writing a session file on every query, as for
    {class}`~meta_package_manager.managers.antidote.Antidote`.
    """

    version_regexes = (r"(?P<version>\d+(?:\.\d+)+)",)
    """Zim prints its version bare, with no name or prefix around it.

    Its `version|--version` case is a single `print -R ${_zversion}`, so the
    regex is anchored on the shape of the version itself. The labeled
    `zimfw version:  ...` string belongs to the separate `zimfw info`
    subcommand and is never what the probe reads.

    ```{code-block} shell-session

    $ zsh -c 'source ~/.zim/init.zsh && zimfw --version'
    1.18.0
    ```
    """

    _INSTALLED_REGEXP = re.compile(
        r"^(?P<package_id>\S+)(?P<flags>(?:\s+\([^)]+\))*)\s*$",
        re.MULTILINE,
    )
    """One module per line: its name, then any parenthesized state flags.

    Zim reports no version: a module is a Git clone tracking a branch, and the
    flags carry state (`external`, `frozen`, `disabled`, `not installed`,
    `unused`) rather than a revision.
    """

    def build_cli(self, *args, **kwargs) -> tuple[str, ...]:
        """Wrap all CLI invocations in the Zsh shell Zim needs.

        The version probe is guarded by a readability test that exits
        successfully when `init.zsh` is absent. Zsh is the default shell on
        macOS and near ubiquitous elsewhere, so an unguarded probe would turn
        every host that merely has Zsh into a manager reporting errors. An
        `init.zsh` that is present but broken still fails loudly.

        ```{note}
        The `**kwargs` accepted by the base class (`auto_pre_args`, `sudo`,
        etc.) are accepted but ignored because every invocation goes through
        the `zsh -c` wrapper and Zim never requires elevated privileges.
        ```
        """
        clean_args = args_cleanup(*args)
        zim_cmd = " ".join(shlex.quote(arg) for arg in clean_args)
        source_path = shlex.quote(str(zim_source_path()))

        if clean_args[:1] == ("--version",):
            probe = (
                f"[[ -r {source_path} ]] || exit 0; "
                f"source {source_path} && zimfw --version"
            )
            return ("zsh", "-c", probe)

        return ("zsh", "-c", f"source {source_path} && zimfw {zim_cmd}")

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        Zim prints one module per line, suffixing each with the state flags
        that apply to it. Two of those flags mean the row is not an installed
        module and are skipped: `(not installed)` for a module the `.zimrc`
        declares but that was never fetched, and `(unused)` for a leftover
        directory no longer declared. `(external)`, `(frozen)` and
        `(disabled)` all still describe installed modules and are kept.

        ```{code-block} shell-session

        $ zsh -c 'source ~/.zim/init.zsh && zimfw list'
        environment
        git
        input
        termtitle
        utility
        duration-info (frozen)
        zsh-completions
        ```
        """
        output = self.run_cli("list")
        for match in self._INSTALLED_REGEXP.finditer(output):
            flags = match.group("flags") or ""
            if any(flag in flags for flag in _ABSENT_FLAGS):
                continue
            yield self.package(id=match.group("package_id"))

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        `zimfw update` re-reads the module set the user's `.zimrc` declares and
        pulls each one.

        ```{code-block} shell-session

        $ zimfw update
        ```
        """
        return self.build_cli("update")
