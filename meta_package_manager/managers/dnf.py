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

from extra_platforms import UNIX_WITHOUT_MACOS

from ..capabilities import search_capabilities, version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class DNF(PackageManager):
    """Fedora's RPM package manager.

    `mpm` reads the inventory through `repoquery` rather than the human-facing
    listing: `--userinstalled` for packages installed on request (dependencies
    pulled in automatically are skipped), `--upgrades` for pending updates and
    `--unneeded` for the orphans, each with a `--queryformat` that joins the
    fields on a private `___MPM___` delimiter so summaries containing spaces stay
    splittable. Every call is forced `--color=never` and `--quiet` for parseable
    output.

    ```{note}
    `outdated` is the one operation that runs two of those queries. `--upgrades`
    answers for *available* packages, so it describes the upgrade candidate and
    never the package installed, and `repoquery` offers no tag for the latter.
    The installed set is therefore read separately and joined on name and
    architecture. It is also the one place versions are reported as `%{evr}`,
    epoch and release included, since an upgrade may move only the release.
    ```

    ```{note}
    `remove` runs `autoremove`, so removing a package also drops the
    dependencies it leaves orphaned. `search` matches names only, with no
    exact or extended mode.
    ```

    The `DNF5` and `YUM` subclasses reuse everything here, differing only in
    the binary and forced arguments.

    Documentation:

    - [DNF command reference](https://dnf.readthedocs.io/en/latest/command_ref.html)
    - [Command equivalences with other managers](https://wiki.archlinux.org/title/Pacman/Rosetta)
    """

    maintenance_note: str | None = (
        "DNF 4 is superseded by "
        "[dnf5](https://github.com/rpm-software-management/dnf5) (Fedora's default "
        "since Fedora 41) but stays maintained for the RHEL 8/9 family; mpm wraps "
        "`dnf5` as a separate manager."
    )

    name = "Fedora DNF"

    homepage_url = "https://github.com/rpm-software-management/dnf"
    logo = "fedora"

    keywords = ("fedora", "redhat", "rhel", "rpm")

    platforms = UNIX_WITHOUT_MACOS

    default_sudo = True

    requirement = ">=4.0.0,<5"
    """Ceiling because `dnf` is no longer dnf4 everywhere.

    Fedora 41 and later ship `/usr/bin/dnf` as a symlink to `dnf5`, and
    {attr}`~meta_package_manager.execution.CLIExecutor.cli_path` returns the
    first name it finds without consulting the version. So this class is handed
    a dnf5 binary on a current Fedora, and the ceiling is what makes it decline
    one, leaving `dnf5` to the `DNF5` subclass that drives it properly. Without
    it the two managers would report the same RPM database twice.
    """

    cli_names: tuple[str, ...] = ("dnf", "dnf4")
    """`dnf4` is the fallback for a host that renamed the dnf4 binary.

    It stays *after* `dnf` deliberately. On RHEL 8 and 9 the only name is `dnf`,
    which is dnf4; on Fedora both exist, and reaching the vestigial
    `/usr/bin/dnf4` there would report a second view of the database `dnf5`
    already covers.
    """

    pre_args: tuple[str, ...] = ("--color=never", "--quiet")

    version_regexes: tuple[str, ...] = (
        r"dnf5\s+version\s+(?P<version>\S+)",
        r"(?P<version>\S+)",
    )
    """dnf4 prints a bare version, so the first pattern is for the *other* binary.

    A `dnf` that is really dnf5 opens `dnf5 version 5.4.3.0`, whose first token
    is the word `dnf5`. Matching that first is what lets the `requirement`
    ceiling above refuse it by version rather than by a parse accident: the bare
    fallback alone would read `dnf5` as the version and report that back to the
    user.

    ```{code-block} shell-session

    $ dnf --version
    4.24.0
      Installed: rpm-0:6.0.2-1.fc44.aarch64 at Fri 04 Sep 2026 08:23:20 AM GMT
      Built    : Fedora Project at Thu 16 Jul 2026 04:13:23 PM GMT
    ```
    """

    _ORPHANS_REGEXP = re.compile(
        r"^(?P<package_id>\S+)-(?:\d+:)?(?P<installed_version>[^-\s]+-[^-\s]+)"
        r"\.(?P<arch>[^.\s]+)$",
        re.MULTILINE,
    )
    """Split `repoquery`'s NEVRA lines (`name-[epoch:]version-release.arch`).

    RPM forbids dashes in the version and release fields, so the last two
    dash-separated fields before the `.arch` suffix are unambiguously
    `version-release`, dashes in the package name notwithstanding.
    """

    _SEARCH_REGEXP = re.compile(
        r"^[ \t]*(?P<package_id>\S+)\.[^.\s]+"
        r"(?:[ \t]+:[ \t]+|\t)"
        r"(?P<description>.+)$"
    )
    """Split a `search` hit into its package id and its summary.

    One pattern for two output shapes, because `yum` fronts either binary. dnf4
    writes `usd.aarch64 : 3D VFX pipeline interchange file format`, while dnf5
    indents the line and separates the two fields with a tab. Matching both is
    what keeps the parser working across the Fedora 41 cutover.

    The trailing `.+` is what captures a summary whole. A `\\S+` there stopped at
    the first space, so every description was stored as its own first word.

    Nothing else is needed to reject the section headers both binaries print
    (dnf4's `===` rules, dnf5's `Matched fields:` lines) or dnf4's metadata
    banner: an anchored match needs a dotted `name.arch` token, and none of them
    carry one.
    """

    DELIMITER = "___MPM___"

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        ```{code-block} shell-session

        $ dnf --color=never --quiet repoquery --userinstalled --qf {format}
        NetworkManager-bluetooth___MPM___1.56.1___MPM___Bluetooth device plugin for NetworkManager___MPM___aarch64
        NetworkManager-team___MPM___1.56.1___MPM___Team device plugin for NetworkManager___MPM___aarch64
        NetworkManager-wifi___MPM___1.56.1___MPM___Wifi plugin for NetworkManager___MPM___aarch64
        ```

        `%{version}` is the upstream version alone: the first of those three is
        installed as `1:1.56.1-2.fc44`, and neither its epoch nor its release
        reaches this listing. `outdated` below reports `%{evr}` instead, which
        carries both.
        """
        qf = ["%{name}", "%{version}", "%{summary}", "%{arch}\n"]
        output = self.run_cli(
            "repoquery", "--userinstalled", "--qf", self.DELIMITER.join(qf)
        )

        for line_package in output.splitlines():
            # remove empty new line
            if not line_package:
                continue
            package_id, installed_version, summary, arch = line_package.split(
                self.DELIMITER
            )
            yield self.package(
                id=package_id,
                description=summary,
                installed_version=installed_version,
                arch=arch,
            )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        Two queries, because one cannot answer both halves. `--upgrades`
        restricts the query to *available* packages, so every field it returns
        describes the upgrade candidate and none of them the installed package.
        `repoquery` exposes no tag for the latter either, `--querytags` listing
        `epoch`, `evr`, `release` and `version` for whichever package matched.
        So the installed side is read once, up front, and joined on name and
        architecture: the pair is what identifies a package on a multilib host,
        where the same name is installed for two of them.

        Both sides are reported as `%{evr}`, the epoch-version-release triplet
        RPM actually orders packages by. A bare `%{version}` would hide the
        release, and a release-only rebuild (`1.21.0-1.fc44` to
        `1.21.0-2.fc44`) is a real upgrade that would then read as an identical
        version on both sides. This is the one operation where that matters,
        which is why `installed` above still reports `%{version}`: changing it
        would rewrite the version string every snapshot carries.

        One format serves both, the summary going unread on the installed pass.
        That keeps the two outputs the same shape, which is what lets either
        block stand in for the other when a documented `FORMAT` placeholder
        leaves the two calls indistinguishable.

        ```{code-block} shell-session

        $ dnf --color=never --quiet repoquery --installed --qf {format}
        librepo___MPM___1.21.0-1.fc44___MPM___Repodata downloading library___MPM___aarch64
        openldap___MPM___2.6.13-1.fc44___MPM___LDAP support libraries___MPM___aarch64
        wireless-regdb___MPM___2026.05.30-1.fc44___MPM___Regulatory database for 802.11 wireless networking___MPM___noarch
        ```

        ```{code-block} shell-session

        $ dnf --color=never --quiet repoquery --upgrades --qf {format}
        librepo___MPM___1.21.0-2.fc44___MPM___Repodata downloading library___MPM___aarch64
        openldap___MPM___2.6.14-1.fc44___MPM___LDAP support libraries___MPM___aarch64
        wireless-regdb___MPM___2026.09.03-1.fc44___MPM___Regulatory database for 802.11 wireless networking___MPM___noarch
        ```
        """
        qf = ["%{name}", "%{evr}", "%{summary}", "%{arch}\n"]
        query_format = self.DELIMITER.join(qf)

        installed_evr: dict[tuple[str, str], str] = {}
        for line_package in self.run_cli(
            "repoquery", "--installed", "--qf", query_format
        ).splitlines():
            if not line_package:
                continue
            name, evr, _summary, arch = line_package.split(self.DELIMITER)
            installed_evr[(name, arch)] = evr

        output = self.run_cli("repoquery", "--upgrades", "--qf", query_format)

        for line_package in output.splitlines():
            # remove empty new line
            if not line_package:
                continue
            package_id, last_version, summary, arch = line_package.split(self.DELIMITER)
            yield self.package(
                id=package_id,
                description=summary,
                # A candidate whose package is somehow not installed keeps a
                # `None` version rather than being dropped: the upgrade is
                # pending either way, and hiding it would be the worse answer.
                installed_version=installed_evr.get((package_id, arch)),
                arch=arch,
                latest_version=last_version,
            )

    @property
    def orphans(self) -> Iterator[Package]:
        """Fetch packages installed as dependencies that nothing requires anymore.

        ```{code-block} shell-session

        $ dnf --color=never --quiet repoquery --unneeded
        bc-0:1.08.2-4.fc44.aarch64
        dos2unix-0:7.5.6-1.fc44.aarch64
        tree-0:2.2.1-4.fc44.aarch64
        ```

        A host reaches this state on its own, but rarely: a fresh install has
        nothing installed-as-a-dependency and then abandoned, which is why the
        rows above were made by marking three leaf packages with
        `dnf mark dependency`. That needs no network and is undone by
        `dnf mark user`.
        """
        output = self.run_cli("repoquery", "--unneeded")
        yield from self.parse_regex_lines(self._ORPHANS_REGEXP, output)

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        ```{caution}
        Search does not support extended or exact matching. So we return the best
        subset of results and let
        {meth}`meta_package_manager.manager.PackageManager.refiltered_search` refine
        them.
        ```

        ```{code-block} shell-session

        $ dnf4 --color=never --quiet search usd
        ========================== Name Exactly Matched: usd ===========================
        usd.aarch64 : 3D VFX pipeline interchange file format
        ========================= Name & Summary Matched: usd ==========================
        libbpf-usdt-devel.noarch : The header for defining USDTs
        python3-usd.aarch64 : Development files for USD
        usd-devel.aarch64 : Development files for USD
        ============================== Name Matched: usd ===============================
        busd.aarch64 : D-Bus bus (broker) implementation
        lvm2-dbusd.noarch : LVM2 D-Bus daemon
        rust-busd+default-devel.noarch : D-Bus bus (broker) implementation
        rust-busd+tracing-subscriber-devel.noarch : D-Bus bus (broker) implementation
        rust-busd-devel.noarch : D-Bus bus (broker) implementation
        usd-libs.aarch64 : Universal Scene Description library
        ```

        dnf5 answers in its own shape, which `yum` also produces wherever that
        name points at dnf5:

        ```{code-block} shell-session

        $ dnf --color=never --quiet search bash
        Matched fields: name (exact)
         bash.aarch64	The GNU Bourne Again shell
        Matched fields: name, summary
         argbash.noarch	Bash argument parsing code generator
         bash-argsparse.noarch	An high level argument parsing library for bash
        ```
        """
        output = self.run_cli("search", query)

        for line in output.splitlines():
            match = self._SEARCH_REGEXP.match(line)
            if match:
                yield self.package(
                    id=match.group("package_id"),
                    description=match.group("description"),
                )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        ```{code-block} shell-session

        $ sudo dnf --color=never --quiet --assumeyes install pip
        ```
        """
        return self.run_cli("--assumeyes", "install", package_id, sudo=True)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all outdated packages.

        ```{code-block} shell-session

        $ sudo dnf --color=never --quiet --assumeyes upgrade
        ```
        """
        return self.build_cli("--assumeyes", "upgrade", sudo=True)

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the provided package.

        ```{code-block} shell-session

        $ sudo dnf --color=never --quiet --assumeyes upgrade pip
        ```
        """
        return self.build_cli("--assumeyes", "upgrade", package_id, sudo=True)

    def remove(self, package_id: str) -> str:
        """Remove one package and one only.

        ```{code-block} shell-session

        $ sudo dnf --color=never --quiet --assumeyes remove pip
        ```
        """
        return self.run_cli("--assumeyes", "remove", package_id, sudo=True)

    def remove_orphan(self, package_id: str) -> str:
        """Remove one package, dropping dependencies it alone pulled in.

        `autoremove` targets the package plus the dependencies that were
        installed to satisfy it and are no longer required by anything else.

        ```{code-block} shell-session

        $ sudo dnf --color=never --quiet --assumeyes autoremove pip
        ```
        """
        return self.run_cli("--assumeyes", "autoremove", package_id, sudo=True)

    def sync(self) -> None:
        """Sync package metadata.

        ```{code-block} shell-session

        $ dnf --color=never --quiet check-update
        ```
        """
        self.run_cli("check-update")

    def cleanup_orphan(self) -> None:
        """Remove every package installed as a dependency and no longer required.

        ```{code-block} shell-session

        $ sudo dnf --color=never --quiet --assumeyes autoremove
        ```
        """
        self.run_cli("--assumeyes", "autoremove", sudo=True)

    def cleanup_cache(self) -> None:
        """Clear the cached packages and repository metadata.

        ```{code-block} shell-session

        $ sudo dnf --color=never --quiet clean all
        ```
        """
        self.run_cli("clean", "all", sudo=True)

    def doctor_cli(self) -> tuple[str, ...]:
        """Generates the CLI running the native self-diagnosis.

        `check` examines the rpm database for problems (duplicates, obsoleted
        packages, unsatisfied dependencies) and exits non-zero when any is found.

        ```{code-block} shell-session

        $ dnf --color=never --quiet check
        ```
        """
        return self.build_cli("check")


class DNF5(DNF):
    """The `dnf5` rewrite of DNF, Fedora's reference package manager since
    Fedora 41.

    Inherits every operation and parser from `DNF`. Its forced arguments drop
    `--color=never` (`dnf5` rejects that option), keeping only `--quiet`.
    """

    # dnf5 is actively developed: clear the maintenance note inherited from DNF.
    maintenance_note = None

    name = "Fedora DNF5"

    homepage_url = "https://github.com/rpm-software-management/dnf5"
    logo = "fedora"

    requirement = ">=5.0.0"
    """dnf5 is the new reference package manager as of Fedora 41."""

    cli_names = ("dnf5",)

    pre_args = ("--quiet",)
    """Reset global options inherited from the `DNF` above.

    Kept for the dnf5 releases that rejected `--color=never`. Current ones
    accept it: `5.4.3.0` exits `0` on the option, where an unknown one exits
    `2`.
    """

    version_regexes = (r"dnf5\s+version\s+(?P<version>\S+)",)
    """`dnf5` opens its own name, where dnf4 answers with a bare version.

    The bare `(?P<version>\\S+)` default reads that first token as the version
    itself, so the manager reported `dnf5` and then refused its own
    `requirement`, taking Fedora's reference package manager out of the pool
    entirely.

    ```{code-block} shell-session

    $ dnf5 --version
    dnf5 version 5.4.3.0
    dnf5 plugin API version 2.0
    libdnf5 version 5.4.3.0
    libdnf5 plugin API version 2.2
    ```
    """


class YUM(DNF):
    """YUM, the package manager DNF superseded.

    On current Fedora and RHEL the `yum` binary is a wrapper around `dnf`.
    `mpm` drives it exactly as `DNF`, only the binary name differs.
    """

    maintenance_note = (
        "The standalone [yum project is archived]"
        "(https://github.com/rpm-software-management/yum); on modern RHEL and Fedora "
        "the `yum` command is a maintained compatibility alias for "
        "[dnf](https://github.com/rpm-software-management/dnf)."
    )

    name = "Fedora YUM"

    homepage_url = "http://yum.baseurl.org"
    logo = "fedora"

    requirement = ">=4.0.0"
    """No ceiling, unlike the `DNF` parent.

    `yum` is a compatibility name rather than a generation: it fronts dnf4 on
    RHEL 8 and 9, and dnf5 on Fedora 41 and later. Both are the manager this
    class is for, so it accepts either, and the inherited `version_regexes`
    already read both shapes.
    """

    cli_names = ("yum",)
