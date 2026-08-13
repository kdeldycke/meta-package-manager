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
import re
from typing import ClassVar

from extra_platforms import LINUX_LIKE, MACOS, WINDOWS

from ..capabilities import search_capabilities, version_not_implemented
from ..manager import PackageManager
from ..version import parse_version

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class Vagrant(PackageManager):
    """Vagrant's box manager, covering the base images it fetches from its registry.

    Vagrant orchestrates virtual machines, which is not package management. Two
    of its subcommand trees are: `vagrant box`, covering versioned base images
    pulled from a registry, and `vagrant plugin`, covering Vagrant's own
    extensions. Only one can be the inventory, and boxes are it. They carry the
    whole operation set, where plugins offer neither an `outdated` nor a search
    of any kind, and a plugin is a RubyGem installed into a private gem home
    rather than something with a registry of its own.

    A package is a box, identified by the bare name the listing prints, which
    may be a registry name like `ubuntu/jammy64`, a purely local name, or a
    full URL. The provider and the architecture are deliberately dropped from
    the identifier.

    ```{note}
    That last point is what makes this a class rather than a definition. Vagrant
    lists one row per *(name, provider, version)* triple, so a box installed in
    three versions appears three times, and the same is true of the outdated
    report. mpm keys a package on its id alone, so both listings are reduced
    here to one entry per name, keeping the newest version installed.
    ```

    ```{caution}
    Every box command reads the registry under `~/.vagrant.d` and needs no
    Vagrantfile, with two exceptions that are avoided rather than handled:
    `vagrant box outdated` inspects only the boxes the *current directory's*
    Vagrantfile declares unless `--global` is passed, and `vagrant box update`
    is scoped the same way unless `--box` names one. Both forced flags are
    therefore load-bearing: without them the answer would depend on where mpm
    happened to be invoked, and would fail outright outside a Vagrant project.

    One piece of ambient state cannot be escaped: Vagrant evaluates the
    Vagrantfile's trigger configuration on every subcommand, so a *malformed*
    Vagrantfile in the working directory breaks even `box list`. Only the
    version probe is immune.
    ```

    ```{note}
    No `upgrade --all`: Vagrant has no command that updates every installed box,
    `box update` addressing either one named box or the current project's. mpm
    backfills it from `outdated` plus the per-box upgrade instead.

    No `sync` either, there being no command that refreshes box metadata without
    also downloading, and the machine-readable output mode is unusable for
    boxes: it emits four lines per box with an empty target column, so nothing
    correlates them back into a record.
    ```

    Documentation: [Vagrant boxes](https://developer.hashicorp.com/vagrant/docs/boxes).
    """

    maintenance_note = (
        "Upstream has slowed: the last stable release is `2.4.9` of August 2025, "
        "though the repository is still committed to. Note also that Vagrant is "
        "distributed under the Business Source License from `2.4.3` onwards, "
        "which some distributions treat as non-free."
    )

    name = "Vagrant"

    homepage_url = "https://www.vagrantup.com"
    logo = "vagrant"

    platforms = LINUX_LIKE, MACOS, WINDOWS

    requirement = ">=2.4.0"
    """The release whose listing groups boxes and renders the architecture as a
    trailing parenthesized segment, which is the shape
    {attr}`_INSTALLED_REGEXP` parses.
    """

    extra_env: ClassVar = {
        # Silences the release-check round-trip Vagrant makes on every command,
        # along with the upgrade banner it prints when one is available.
        "VAGRANT_CHECKPOINT_DISABLE": "1",
    }

    version_regexes = (r"^Vagrant[ \t]+(?P<version>\S+)$",)
    r"""Search the version right after the `Vagrant ` string.

    ```{code-block} shell-session

    $ vagrant --version
    Vagrant 2.4.9
    ```

    Note the dashes: `vagrant version` without them is a different command that
    queries the network for the latest release.
    """

    _INSTALLED_REGEXP = re.compile(
        r"^(?P<package_id>\S+)[ \t]+\((?P<provider>[^,()]+),[ \t]+"
        r"(?P<installed_version>[^,()]+?)(?:,[ \t]+\([^()]*\))?\)$",
    )
    """One box row: the name, then a parenthesized provider and version, and on
    recent Vagrants a further parenthesized architecture the pattern discards.
    """

    _OUTDATED_REGEXP = re.compile(
        r"^\*[ \t]+'(?P<package_id>[^']+)'[ \t]+for[ \t]+'[^']+'[ \t]+is outdated!"
        r"[ \t]+Current:[ \t]+(?P<installed_version>.+?)\.[ \t]+"
        r"Latest:[ \t]+(?P<latest_version>\S+)$",
    )
    """A box with an update pending. The report interleaves three other shapes,
    for a box that is current, one that was never added from a catalog and one
    whose metadata failed to load: none carries an update, and none matches.
    """

    def _newest_per_box(
        self,
        rows: Iterator[tuple[str, str, str | None]],
    ) -> Iterator[Package]:
        """Reduce `(name, installed, latest)` rows to one package per box.

        Vagrant reports a row per version and provider, so a box installed
        several times over appears several times. Only the newest installed
        version is kept, which is the one a bare `vagrant box update --box`
        acts on.
        """
        best: dict[str, tuple[str, str | None]] = {}
        for package_id, installed, latest in rows:
            current = best.get(package_id)
            if current is None or parse_version(installed) > parse_version(current[0]):
                best[package_id] = (installed, latest)
        for package_id, (installed, latest) in best.items():
            yield self.package(
                id=package_id,
                installed_version=installed,
                latest_version=latest,
            )

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        ```{code-block} shell-session

        $ vagrant box list
        linuxmint-21.3-cinnamon-64bit (hyperv, 0)
        mintv1                        (hyperv, 0)
        wolvverine/LinuxMintCinnamon  (hyperv, 1.1, (amd64))
        ```
        """
        output = self.run_cli("box", "list")
        yield from self._newest_per_box(
            (match.group("package_id"), match.group("installed_version"), None)
            for match in map(self._INSTALLED_REGEXP.match, output.splitlines())
            if match
        )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        `--global` is what makes this answer for the machine: without it Vagrant
        reports only the boxes the working directory's Vagrantfile declares, and
        fails where there is none.

        ```{caution}
        Vagrant exits zero whether or not updates were found, by an explicit
        upstream decision, so the listing itself is the only signal.
        ```

        ```{code-block} shell-session

        $ vagrant box outdated --global
        * 'ubuntu/jammy64' for 'virtualbox' is outdated! Current: 20231012.0.0. Latest: 20240126.0.0
        * 'ubuntu/jammy64' for 'virtualbox' is outdated! Current: 20230914.0.0. Latest: 20240126.0.0
        * 'ubuntu/jammy64' for 'virtualbox' is outdated! Current: 20230616.0.0. Latest: 20240126.0.0
        ```
        """
        output = self.run_cli("box", "outdated", "--global")
        yield from self._newest_per_box(
            (
                match.group("package_id"),
                match.group("installed_version"),
                match.group("latest_version"),
            )
            for match in map(self._OUTDATED_REGEXP.match, output.splitlines())
            if match
        )

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        Boxes have no search of their own: the query goes to the registry
        through Vagrant's `cloud` command tree, which answers anonymously
        unless credentials are explicitly requested.

        ```{caution}
        Search does not support extended or exact matching.
        ```

        ```{code-block} console

        $ vagrant cloud search ubuntu --json
        [
          {
            "name": "ubuntu/jammy64",
            "version": "20240126.0.0",
            "downloads": "1,234,567",
            "providers": "virtualbox",
            "architectures": "amd64"
          }
        ]
        ```
        """
        output = self.run_cli("cloud", "search", query, "--json")
        for entry in json.loads(output) if output.strip() else ():
            package_id = entry.get("name")
            if not package_id:
                continue
            yield self.package(id=package_id, latest_version=entry.get("version"))

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        ```{code-block} shell-session

        $ vagrant box add ubuntu/jammy64
        ```
        """
        return self.run_cli("box", "add", package_id)

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the package provided as parameter.

        `--box` names the box explicitly, which is what lets this run outside a
        Vagrant project: the bare form updates whatever the current directory's
        Vagrantfile declares instead.

        ```{code-block} shell-session

        $ vagrant box update --box ubuntu/jammy64
        ```
        """
        return self.build_cli("box", "update", "--box", package_id)

    def remove(self, package_id: str) -> str:
        """Removes a package.

        `--all` removes every version, provider and architecture of the box in
        one call. It is what keeps this addressable by a bare name: without it
        Vagrant refuses a box held in several versions and demands an explicit
        `--box-version`. `--force` skips the confirmation Vagrant would
        otherwise ask for a box still attached to a machine.

        ```{code-block} shell-session

        $ vagrant box remove --force --all ubuntu/jammy64
        ```
        """
        return self.run_cli("box", "remove", "--force", "--all", package_id)

    def cleanup_orphan(self) -> None:
        """Removes outdated versions of installed boxes.

        Keeps the newest version of each box and drops the rest. `--force`
        skips the confirmation Vagrant asks when a stale version is still
        attached to a machine, which would otherwise abort for want of a
        terminal.

        ```{code-block} shell-session

        $ vagrant box prune --force
        ```
        """
        self.run_cli("box", "prune", "--force")
