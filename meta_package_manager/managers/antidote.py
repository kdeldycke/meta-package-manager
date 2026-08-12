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

import json
import os
import re
import shlex
from pathlib import Path
from typing import ClassVar

from click_extra.execution import args_cleanup
from extra_platforms import LINUX_LIKE, MACOS

from ..capabilities import version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


_ZDOTDIR = os.environ.get("ZDOTDIR", str(Path.home()))
"""Base directory Antidote's own installation instructions derive from.

Antidote clones itself into `${ZDOTDIR:-$HOME}/.antidote`, so the same
fallback resolves the manual install on a host that sets no `ZDOTDIR`.
"""

_HOMEBREW_PREFIXES = tuple(
    prefix
    for prefix in (
        os.environ.get("HOMEBREW_PREFIX"),
        "/opt/homebrew",
        "/usr/local",
        "/home/linuxbrew/.linuxbrew",
    )
    if prefix
)
"""Homebrew roots to probe, the environment's own answer first.

Homebrew installs Antidote as package data rather than as a binary, so its
copy is only reachable through the prefix: Apple Silicon, Intel and Linuxbrew
each use a different one.
"""

_SOURCE_CANDIDATES = (
    Path(_ZDOTDIR) / ".antidote" / "antidote.zsh",
    *(
        Path(prefix) / "opt" / "antidote" / "share" / "antidote" / "antidote.zsh"
        for prefix in _HOMEBREW_PREFIXES
    ),
)
"""Where `antidote.zsh` sits, in the order Antidote's own install page lists:
the manual Git clone first, then each Homebrew prefix."""


def antidote_source_path() -> Path:
    """Locate the `antidote.zsh` file every invocation sources.

    Falls back to the documented clone location when none of the candidates
    exists, so the built command stays well-formed and simply fails to source,
    which is what makes the version probe double as Antidote's presence check.
    """
    for candidate in _SOURCE_CANDIDATES:
        if candidate.is_file():
            return candidate
    return _SOURCE_CANDIDATES[0]


class Antidote(PackageManager):
    """Antidote is a Zsh plugin manager, successor to `antibody`.

    Antidote clones each bundle from GitHub or any other forge into
    `$ANTIDOTE_HOME`, and records it in the user's `.zsh_plugins.txt` file.
    Packages are identified by the `user/repo` slug Antidote both reports and
    accepts, which is the id mpm keys them on.

    ```{caution}
    `antidote` is a shell function, not a standalone binary: the `antidote`
    script shipped in the repository carries a Zsh shebang but is not
    executable, and Homebrew installs it as package data under
    `share/antidote` rather than linking it into `bin`. Every invocation is
    therefore wrapped in `zsh -c 'source <antidote.zsh> && antidote <args>'`.
    Zsh is the manager's CLI, and Antidote's own presence is established by
    the version probe: a host with Zsh but no Antidote fails to source and
    reports no version, which leaves the manager unavailable.
    ```

    ```{note}
    No `search`: Antidote resolves bundles straight from forge URLs and
    indexes no registry to search.
    ```

    ```{note}
    No `upgrade_one`: `antidote update` takes no bundle argument, only the
    `--self` and `--bundles` scope flags, so a single bundle cannot be
    targeted. mpm auto-skips the operation and `upgrade --all` still works.
    ```

    Documentation: [antidote.sh](https://antidote.sh).
    """

    homepage_url = "https://antidote.sh"
    logo = "zsh"

    platforms = LINUX_LIKE, MACOS

    requirement = ">=2.2.0"
    """First release whose `list --jsonl` and `update --dry-run` are both sound.

    Both landed in `2.0.0`, but each carried a defect this implementation
    depends on being fixed: `2.1.1` repaired `list --jsonl` emitting invalid
    JSON whenever a value held a quote, backslash or control character, and
    `2.2.0` stopped `update --dry-run` deepening shallow clones, a permanent
    side effect that made a dry run something other than a query. `2.2.0` also
    fixed `antidote update` reporting success when a worker had failed, which
    is the exit code mpm reads to mark the operation.
    """

    cli_names = ("zsh",)
    """Zsh is the binary mpm actually executes.

    Antidote is a shell function defined by an `antidote.zsh` file that is
    sourced, never executed, so it cannot serve as the manager's CLI: mpm
    requires an executable. Keying the manager on Zsh instead makes the
    version probe the presence check, since sourcing an absent `antidote.zsh`
    yields no version and leaves the manager unavailable.
    """

    extra_env: ClassVar = {
        "NO_COLOR": "1",
        "SHELL_SESSIONS_DISABLE": "1",
    }
    """Antidote gives `NO_COLOR` precedence over every other color signal, so
    the parsers see clean text. `SHELL_SESSIONS_DISABLE` keeps macOS' Zsh
    session bookkeeping from writing a session file on every query."""

    version_regexes = (r"antidote version (?P<version>\S+)",)
    """Antidote appends the short commit of its own checkout to the release it
    reports.

    ```{code-block} shell-session

    $ zsh -c 'source ~/.antidote/antidote.zsh && antidote --version'
    antidote version 2.3.0 (9bb69ab)
    ```
    """

    _OUTDATED_REGEXP = re.compile(
        r"^antidote: update available: "
        r"(?P<package_id>\S+) (?P<installed_version>\S+) -> (?P<latest_version>\S+)$",
    )
    """The one dry-run line announcing a bundle behind its remote.

    Anchored on the whole line so the commit log Antidote prints underneath
    each announcement, which is `<sha> <subject>` shaped and would otherwise
    match loosely, is not mistaken for another bundle.
    """

    def build_cli(self, *args, **kwargs) -> tuple[str, ...]:
        """Wrap all CLI invocations in the Zsh shell Antidote needs.

        The version probe is guarded by a readability test that exits
        successfully when `antidote.zsh` is absent. Zsh is the default shell
        on macOS and near ubiquitous elsewhere, so an unguarded probe would
        turn every host that merely has Zsh into a manager reporting errors. An
        `antidote.zsh` that is present but broken still fails loudly.

        ```{note}
        The `**kwargs` accepted by the base class (`auto_pre_args`, `sudo`,
        etc.) are accepted but ignored because every invocation goes through
        the `zsh -c` wrapper and Antidote never requires elevated privileges.
        ```
        """
        clean_args = args_cleanup(*args)
        antidote_cmd = " ".join(shlex.quote(arg) for arg in clean_args)
        source_path = shlex.quote(str(antidote_source_path()))

        if clean_args[:1] == ("--version",):
            probe = (
                f"[[ -r {source_path} ]] || exit 0; "
                f"source {source_path} && antidote --version"
            )
            return ("zsh", "-c", probe)

        return ("zsh", "-c", f"source {source_path} && antidote {antidote_cmd}")

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        Antidote emits one JSON object per line rather than a single array, so
        the listing is decoded line by line. The `sha` reported for a bundle is
        the Git commit its clone is checked out at, which is the only revision
        Antidote records: a bundle is tracked by branch unless the user pins it
        with a `pin:` annotation.

        ```{code-block} shell-session

        $ zsh -c 'source ~/.antidote/antidote.zsh && antidote list --jsonl'
        {"url":"https://github.com/rupa/z","repo":"rupa/z","path":"/home/kev/.cache/antidote/github.com/rupa/z","sha":"d37a763a6a30e1b32766fecc3b8ffd6127f8a0fd"}
        {"url":"https://github.com/zsh-users/zsh-completions","repo":"zsh-users/zsh-completions","path":"/home/kev/.cache/antidote/github.com/zsh-users/zsh-completions","sha":"729a2408fb129bcda7e8a21ae7bf349fe295b634"}
        ```
        """
        output = self.run_cli("list", "--jsonl")
        for line in output.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                # Antidote reports an empty bundle store as a plain sentence.
                continue
            try:
                bundle = json.loads(line)
            except json.JSONDecodeError:
                continue
            package_id = bundle.get("repo")
            if not package_id:
                continue
            yield self.package(id=package_id, installed_version=bundle.get("sha"))

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        `--dry-run` fetches each bundle's remote and reports what an update
        would move, without touching a single working tree. Both revisions are
        the short commits Antidote prints, so an outdated bundle reads as a
        commit-to-commit move rather than a version bump: bundles are tracked
        by branch, and Antidote records no version of its own.

        ```{code-block} shell-session

        $ zsh -c 'source ~/.antidote/antidote.zsh && antidote update --dry-run'
        Checking for bundle updates (dry run)...
        antidote: checking for updates: rupa/z
        antidote: checking for updates: zsh-users/zsh-completions
        Waiting for bundle updates to complete...

        Bundle rupa/z update check complete.
        antidote: update available: rupa/z b82ac78 -> d37a763
        d37a763 Escape calls for sed and awk in case someone aliased them (#264)
        703bb54 avoid issues when `date` has been aliased
        6ba0722 avoid issues when `env` has been aliased

        Dry run complete. No changes were made.

        antidote: skipping self-update (dry run)
        ```
        """
        output = self.run_cli("update", "--dry-run")
        yield from self.parse_regex_lines(self._OUTDATED_REGEXP, output)

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        `install` both clones the bundle and appends it to the user's
        `.zsh_plugins.txt`, so a package installed through mpm is loaded by the
        next shell instead of sitting on disk unreferenced.

        ```{code-block} shell-session

        $ antidote install rupa/z
        Adding bundle to '/home/kev/.zsh_plugins.txt':
        rupa/z
        ```
        """
        return self.run_cli("install", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        ```{note}
        Scoped to `--bundles` so the update stays a package operation.
        A bare `antidote update` also updates Antidote itself, which is the
        manager rather than a package, and which would mean a Git pull inside
        a Homebrew keg on a host that installed it that way.
        ```

        ```{code-block} shell-session

        $ antidote update --bundles
        ```
        """
        return self.build_cli("update", "--bundles")

    def remove(self, package_id: str) -> str:
        """Remove one package.

        `purge` is the exact counterpart of {meth}`Antidote.install`: it drops
        the clone and comments the bundle out of the user's
        `.zsh_plugins.txt`, so the next shell no longer loads it.

        ```{code-block} shell-session

        $ antidote purge rupa/z
        Removed 'rupa/z'.
        Bundle 'rupa/z' was commented out in '/home/kev/.zsh_plugins.txt'.
        ```
        """
        return self.run_cli("purge", package_id)
