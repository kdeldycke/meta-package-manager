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


def antigen_source_path() -> Path:
    """Locate the `antigen.zsh` file every invocation sources.

    Antigen documents no install location of its own: its README has the user
    `curl -L git.io/antigen > antigen.zsh` into a directory of their choosing,
    then `source /path-to-antigen/antigen.zsh`. Discovery is therefore
    best-effort over the two conventional spots plus `$ADOTDIR`, and a user who
    keeps it anywhere else simply leaves the manager unavailable rather than
    seeing it misbehave.

    Falls back to the first candidate when none exists, so the built command
    stays well-formed and fails to source, which is what makes the version
    probe double as Antigen's presence check.
    """
    candidates = [Path.home() / "antigen.zsh", Path.home() / ".antigen" / "antigen.zsh"]
    adotdir = os.environ.get("ADOTDIR")
    if adotdir:
        candidates.insert(0, Path(adotdir) / "antigen.zsh")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


class Antigen(PackageManager):
    """Antigen is a plugin manager for Zsh.

    Bundles are declared in the user's `.zshrc` with `antigen bundle` calls,
    then cloned under `$ADOTDIR`. Packages are identified by the short
    `owner/repo` name Antigen reports, which is the id mpm keys them on.

    ```{caution}
    `antigen` is a shell function, not a standalone binary: it is defined by
    sourcing an `antigen.zsh` file, so it cannot serve as the manager's CLI.
    Every invocation is therefore wrapped in `zsh -c`. Zsh is the binary mpm
    executes, and Antigen's own presence is established by the version probe.

    Unlike its siblings, Antigen documents no canonical install path, so
    {func}`antigen_source_path` can only guess at the conventional ones. A user
    who sources it from elsewhere leaves the manager unavailable.
    ```

    ```{caution}
    No `install`: Antigen materializes exactly the bundle set the user's own
    `.zshrc` declares. `antigen bundle` clones and loads a bundle for the
    current shell only, writing nothing back, so a package installed through
    mpm would vanish with the process. Installing one for real would mean mpm
    editing the user's `.zshrc`, which is configuration mpm does not own.
    ```

    ```{note}
    No `outdated`: Antigen compares nothing against its remotes short of
    performing the update. `upgrade --all` still works, and mpm auto-skips the
    operation.
    ```

    Documentation: [antigen](https://github.com/zsh-users/antigen).
    """

    name = "Zsh Antigen"

    homepage_url = "https://github.com/zsh-users/antigen"
    logo = "zsh"

    platforms = LINUX_LIKE, MACOS

    requirement = ">=2.0.0"
    """The `2.x` series is where `list`, `purge` and `update` settled as the
    subcommands this class drives, alongside the `$ADOTDIR` layout.
    """

    cli_names = ("zsh",)
    """Zsh is the binary mpm actually executes.

    Antigen is a shell function defined by an `antigen.zsh` file that is
    sourced, never executed, so it cannot serve as the manager's CLI: mpm
    requires an executable. Keying the manager on Zsh instead makes the version
    probe the presence check.
    """

    extra_env: ClassVar = {
        "NO_COLOR": "1",
        "SHELL_SESSIONS_DISABLE": "1",
    }
    """`SHELL_SESSIONS_DISABLE` keeps macOS' Zsh session bookkeeping from
    writing a session file on every query, as for
    {class}`~meta_package_manager.managers.antidote.Antidote`.
    """

    version_cli_options = ("version",)
    """Antigen spells it as a subcommand: it defines an `antigen-version`
    function reached as `antigen version`, and recognizes no `--version` flag.
    """

    version_regexes = (r"Antigen\s+v?(?P<version>\S+)",)
    """Antigen prints its release followed by the short commit it was built
    from.

    The optional `v` absorbs the tag prefix its release builds carry. A copy
    taken from the development branch reports the literal string `develop`
    there instead of a version, which parses to nothing and correctly leaves
    the manager unavailable.

    ```{code-block} shell-session

    $ zsh -c 'source ~/antigen.zsh && antigen version'
    Antigen v2.2.3 (0554db1)
    Revision date: 2026-07-14 16:52:45 +0100
    ```
    """

    def build_cli(self, *args, **kwargs) -> tuple[str, ...]:
        """Wrap all CLI invocations in the Zsh shell Antigen needs.

        The version probe is guarded by a readability test that exits
        successfully when `antigen.zsh` is absent. Zsh is the default shell on
        macOS and near ubiquitous elsewhere, so an unguarded probe would turn
        every host that merely has Zsh into a manager reporting errors.

        ```{note}
        The `**kwargs` accepted by the base class (`auto_pre_args`, `sudo`,
        etc.) are accepted but ignored because every invocation goes through
        the `zsh -c` wrapper and Antigen never requires elevated privileges.
        ```
        """
        clean_args = args_cleanup(*args)
        antigen_cmd = " ".join(shlex.quote(arg) for arg in clean_args)
        source_path = shlex.quote(str(antigen_source_path()))

        if clean_args[:1] == ("version",):
            probe = (
                f"[[ -r {source_path} ]] || exit 0; "
                f"source {source_path} && antigen version"
            )
            return ("zsh", "-c", probe)

        return ("zsh", "-c", f"source {source_path} && antigen {antigen_cmd}")

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        `--simple` is the listing format that prints one bare bundle name per
        line. Antigen's default `--short` format appends ` @ <revision>` to
        each, but that revision is the tracked *branch* (literally `master` for
        any bundle not pinned to one), not a version, so the simple form is
        what mpm parses.

        ```{code-block} shell-session

        $ zsh -c 'source ~/antigen.zsh && antigen list --simple'
        zsh-users/zsh-syntax-highlighting
        zsh-users/zsh-completions
        zsh-users/zsh-history-substring-search
        ```
        """
        output = self.run_cli("list", "--simple")
        for line in output.splitlines():
            bundle = line.strip()
            if bundle:
                yield self.package(id=bundle)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        ```{code-block} shell-session

        $ antigen update
        ```
        """
        return self.build_cli("update")

    def remove(self, package_id: str) -> str:
        """Remove one package.

        `purge` drops the bundle's clone from the filesystem. It leaves the
        user's `.zshrc` untouched, so a bundle still declared there is cloned
        again by the next shell: the removal is of the installed copy, not of
        the declaration.

        ```{code-block} shell-session

        $ antigen purge zsh-users/zsh-completions --force
        ```
        """
        return self.run_cli("purge", package_id, "--force")
