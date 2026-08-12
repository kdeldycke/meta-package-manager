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


_SECTION_HEADERS = frozenset({"Plugins", "Themes"})
"""Underlined headers `omf list` prints above each of its two sections.

They are the only tokens in the listing that are not package names, so
filtering them out is what turns the column-formatted output into an
inventory.
"""


def omf_source_path() -> Path:
    """Locate the `init.fish` file every invocation sources.

    Oh My Fish installs itself into `$OMF_PATH`, falling back to
    `~/.local/share/omf` when the variable is unset, as its own installer does.
    The path is returned whether or not it exists, so the built command stays
    well-formed and simply fails to source, which is what makes the version
    probe double as Oh My Fish's presence check.
    """
    omf_path = os.environ.get("OMF_PATH") or str(
        Path.home() / ".local" / "share" / "omf"
    )
    return Path(omf_path) / "init.fish"


class OhMyFish(PackageManager):
    """Oh My Fish is a framework and plugin manager for the Fish shell.

    Packages are cloned under `$OMF_PATH` and recorded in the user's bundle
    file. Oh My Fish manages two kinds of package, plugins and themes, and
    reports both from one listing: mpm yields them together, since a name is
    unique across the two and every mutating command takes either.

    ```{caution}
    `omf` is a Fish function, not a standalone binary: it is defined by
    sourcing `$OMF_PATH/init.fish`, so it cannot serve as the manager's CLI.
    Every invocation is therefore wrapped in `fish -c`. Fish is the binary mpm
    executes, and Oh My Fish's own presence is established by the version
    probe: a host with Fish but no Oh My Fish fails to source and reports no
    version, which leaves the manager unavailable.
    ```

    ```{note}
    No `outdated`: Oh My Fish compares nothing against its remotes short of
    performing the update. `upgrade --all` still works, and mpm auto-skips the
    operation.
    ```

    ```{note}
    No `search`: `omf search` exists and would map cleanly, but its results are
    printed by a private `__omf.cli.search.output` helper whose format no
    upstream sample pins down, so declaring it would mean guessing at a parser.
    ```

    Documentation: [Oh My Fish](https://github.com/oh-my-fish/oh-my-fish).
    """

    id = "oh-my-fish"

    name = "Fish Oh My Fish"

    homepage_url = "https://github.com/oh-my-fish/oh-my-fish"

    platforms = LINUX_LIKE, MACOS

    requirement = ">=6.0.0"
    """The `6.x` series is where this command set settled.

    `omf list`, `omf install`, `omf remove` and the package-scoped `omf update`
    all predate it, but `6.0.0` is the release that moved the framework to
    `$OMF_PATH` with the `init.fish` entry point this manager sources.
    """

    cli_names = ("fish",)
    """Fish is the binary mpm actually executes.

    Oh My Fish is a shell function defined by an `init.fish` file that is
    sourced, never executed, so it cannot serve as the manager's CLI: mpm
    requires an executable. Keying the manager on Fish instead makes the
    version probe the presence check.
    """

    extra_env: ClassVar = {"NO_COLOR": "1"}
    """Oh My Fish underlines its section headers through Fish's `set_color`,
    which `NO_COLOR` disables so the listing parses as clean text.
    """

    version_regexes = (r"Oh My Fish version (?P<version>\S+)",)
    """
    Oh My Fish derives what it reports from `git describe --tags --match 'v*'
    --always`, with the leading `v` cut off, so a checkout sitting on a release
    tag reports that release and one ahead of it reports a describe string.

    ```{code-block} shell-session

    $ fish -c 'source ~/.local/share/omf/init.fish; and omf --version'
    Oh My Fish version 7
    ```
    """

    def build_cli(self, *args, **kwargs) -> tuple[str, ...]:
        """Wrap all CLI invocations in the Fish shell Oh My Fish needs.

        The version probe is guarded by a readability test that exits
        successfully when `init.fish` is absent, so a host that merely has Fish
        installed does not turn into a manager reporting errors. An `init.fish`
        that is present but broken still fails loudly.

        ```{note}
        The `**kwargs` accepted by the base class (`auto_pre_args`, `sudo`,
        etc.) are accepted but ignored because every invocation goes through
        the `fish -c` wrapper and Oh My Fish never requires elevated
        privileges.
        ```
        """
        clean_args = args_cleanup(*args)
        omf_cmd = " ".join(shlex.quote(arg) for arg in clean_args)
        source_path = shlex.quote(str(omf_source_path()))

        if clean_args[:1] == ("--version",):
            probe = (
                f"test -r {source_path}; or exit 0; "
                f"source {source_path}; and omf --version"
            )
            return ("fish", "-c", probe)

        return ("fish", "-c", f"source {source_path}; and omf {omf_cmd}")

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        Oh My Fish pipes both of its listings through `column`, so packages
        arrive several per line in a layout that depends on the terminal width,
        under an underlined `Plugins` and `Themes` header. Every token that is
        not one of those two headers is a package name: names carry no
        whitespace, which is what makes splitting on it sound.

        No version is reported for any of them: a package is a Git clone
        tracking a branch, and Oh My Fish records no revision per package.

        ```{code-block} console

        $ fish -c 'source ~/.local/share/omf/init.fish; and omf list'
        Plugins
        bang-bang     brew          fish-spec     osx
        percol        pyenv         tab           z

        Themes
        agnoster      bobthefish    default       scorphish
        ```

        The block above is an illustration rather than a harvested fixture: the
        column layout is computed from the terminal width, so no sample can be
        byte-accurate across hosts.
        """
        output = self.run_cli("list")
        for token in output.split():
            if token in _SECTION_HEADERS:
                continue
            yield self.package(id=token)

    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        A theme is additionally set as the active one by Oh My Fish itself,
        which is its own behavior and not something mpm asks for.

        ```{code-block} shell-session

        $ omf install z
        ```
        """
        return self.run_cli("install", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        ```{note}
        A bare `omf update` also updates the Oh My Fish core, which is the
        manager rather than a package. The core is left in, deliberately:
        unlike Antidote's `--bundles`, Oh My Fish offers no flag to scope an
        update to packages only, and naming every package instead would race
        the listing.
        ```

        ```{code-block} shell-session

        $ omf update
        ```
        """
        return self.build_cli("update")

    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade one package.

        Naming a package keeps the core out of the update: Oh My Fish only
        refreshes itself when `omf` is one of the names passed.

        ```{code-block} shell-session

        $ omf update z
        ```
        """
        return self.build_cli("update", package_id)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        ```{code-block} shell-session

        $ omf remove z
        ```
        """
        return self.run_cli("remove", package_id)
