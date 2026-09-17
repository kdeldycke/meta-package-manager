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

from extra_platforms import LINUX_LIKE

from ..capabilities import search_capabilities
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class MicroDNF(PackageManager):
    """A minimal `dnf` written in C on top of libdnf, for containers.

    The minimal container images of the RHEL family install it instead of
    `dnf`: [AlmaLinux 10's](https://github.com/AlmaLinux/container-images/blob/09f5ebe70432a7a932b5cfa6e5e5725654aa6b6d/Containerfiles/10/Containerfile.minimal#L4-L19)
    lists `microdnf` and no `dnf`. On a host that has both, `microdnf` and
    [`dnf`](dnf.md) read the same RPM database, so their listings overlap.

    ```{note}
    On Fedora, and on RHEL releases after 10, the dnf5 package takes over the
    `microdnf` name as a symlink to `dnf5`
    ([dnf5.spec](https://github.com/rpm-software-management/dnf5/blob/cfdbb345396b2cfed7afe69cf70b3aba95ce7ee4/dnf5.spec#L1161-L1163)).
    No `microdnf` RPM package is installed there, so this manager reports no
    version and leaves that binary to [`dnf5`](dnf5.md).
    ```

    ```{caution}
    `microdnf` keeps one system-wide cache under `/var/cache/yum`, and only root
    can write to it. As a regular user, every query fails while
    `/var/cache/yum/metadata` is missing, which is the state `clean all` leaves.
    `search` and `outdated` also fail once the repository metadata expires,
    with `failed to obtain lock 'metadata'`. `mpm --microdnf sync` runs
    `makecache` with `sudo` to rebuild the cache.
    ```

    `microdnf` has no autoremove and no self-check, so `mpm` offers no orphan
    operations and no `doctor` for it. Its `leaves` command is no substitute:
    it lists every installed package that nothing else requires, including the
    packages installed on request.
    """

    maintenance_note = (
        "Superseded by [dnf5](https://github.com/rpm-software-management/dnf5) on "
        "Fedora, and on RHEL releases after 10. The C implementation stays "
        "maintained for RHEL 10 and older, whose minimal images ship it; mpm wraps "
        "`dnf5` as a separate manager."
    )

    name = "microdnf"

    repository_url = "https://github.com/rpm-software-management/microdnf"
    logo = "fedora"

    platforms = LINUX_LIKE

    default_sudo = True

    requirement = ">=3.8.0"
    """`3.8.0` is the first release with the `makecache` command that `sync` runs
    ([rpm-software-management/microdnf@e2d56ee](https://github.com/rpm-software-management/microdnf/commit/e2d56eefd58149a2d80b914b87171a35ee51146a)).
    Everything else is older: `--assumeno`, which `outdated` needs, shipped in
    `3.7.0`, and `repoquery` in `3.4.0`.
    """

    version_cli = "rpm"
    """`microdnf` has no version option. It ignores `--version`, prints its usage
    and `No command specified` to stderr, and exits `1`. So the probe asks RPM
    for the version of the `microdnf` package instead.

    `rpm --query` matches package names, never the capabilities a package
    provides. That is why the probe finds nothing where dnf5 provides a
    `microdnf` symlink.
    """

    version_cli_options = ("--query", "--queryformat", "%{VERSION}", "microdnf")

    version_regexes = (r"^(?P<version>\d\S*)$",)
    """Anchored at both ends: a host without the package answers with the
    sentence `package microdnf is not installed`, which must match nothing.

    ```{code-block} shell-session

    $ rpm --query --queryformat %{VERSION} microdnf
    3.10.1
    ```
    """

    _NEVRA_REGEXP = re.compile(
        r"^(?P<name>\S+)-(?P<evr>(?:\d+:)?[^-\s]+-[^-\s]+)\.(?P<arch>[^.\s]+)$",
        re.MULTILINE,
    )
    """Split a `name-[epoch:]version-release.arch` line.

    RPM forbids dashes in the version and the release, so the last two
    dash-separated fields before the `.arch` suffix are always those two,
    whatever dashes the name carries. `microdnf` prints the epoch only when it
    is not zero. The version keeps it, so a pinned install can pass it back.

    Every listing prints its rows sorted by name, then by version, so the last
    row of a name is its newest build.
    """

    _SECTION_REGEXP = re.compile(r"^(?P<section>[A-Z][a-z]+):\s*$")
    """Match a section heading of the transaction table, like `Upgrading:`."""

    _ROW_REGEXP = re.compile(r"^ (?P<nevra>\S+)")
    """Match a package row of the transaction table, indented by one space."""

    _REPLACING_REGEXP = re.compile(r"^\s+replacing\s+(?P<nevra>\S+)")
    """Match the child row naming the installed package the row above replaces.

    Its indentation varies: the last child of the table gets one more space.
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        ```{code-block} shell-session

        $ microdnf repoquery --installed
        NetworkManager-1:1.56.0-2.el10_2.aarch64
        NetworkManager-libnm-1:1.56.0-2.el10_2.aarch64
        NetworkManager-tui-1:1.56.0-2.el10_2.aarch64
        almalinux-gpg-keys-10.2-21.el10.aarch64
        almalinux-release-10.2-21.el10.aarch64
        almalinux-repos-10.2-21.el10.aarch64
        alternatives-1.30-2.el10.aarch64
        attr-2.5.2-5.el10.aarch64
        ```
        """
        output = self.run_cli("repoquery", "--installed", must_succeed=True)
        for match in self._NEVRA_REGEXP.finditer(output):
            yield self.package(
                id=match["name"],
                installed_version=match["evr"],
                arch=match["arch"],
            )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        `microdnf` has no command that lists pending updates. So `mpm` reads the
        transaction `upgrade` would run, which `--assumeno` refuses before
        anything changes. The command exits `0` either way, with
        `Operation aborted.` after the table, or `Nothing to do.` alone.

        An upgraded package is a row under `Upgrading:`, followed by a
        `replacing` row that names the installed version. An install-only
        package, like the kernel, is a row under `Installing:` instead: RPM
        installs its new version beside the old one. New dependencies show up
        in that section too, so a second query reads which of those names are
        installed, and skips the others.

        ```{code-block} shell-session

        $ microdnf --assumeno upgrade
        Package                                             Repository     Size
        Installing:
         kernel-6.12.0-211.53.1.el10_2.aarch64              baseos       1.7 MB
         kernel-core-6.12.0-211.53.1.el10_2.aarch64         baseos      19.9 MB
         kernel-modules-6.12.0-211.53.1.el10_2.aarch64      baseos      28.3 MB
         kernel-modules-core-6.12.0-211.53.1.el10_2.aarch64 baseos      26.6 MB
        Upgrading:
         rsync-3.5.0-3.el10_2.aarch64                       baseos     474.3 kB
          replacing rsync-3.4.4-1.el10_2.aarch64
         tar-2:1.35-13.el10_2.aarch64                       baseos     884.5 kB
           replacing tar-2:1.35-11.el10.aarch64
        Transaction Summary:
         Installing:        4 packages
         Reinstalling:      0 packages
         Upgrading:         2 packages
         Obsoleting:        0 packages
         Removing:          0 packages
         Downgrading:       0 packages
        Operation aborted.
        ```

        ```{code-block} shell-session

        $ microdnf repoquery --installed kernel kernel-core kernel-modules kernel-modules-core
        kernel-6.12.0-211.47.1.el10_2.aarch64
        kernel-core-6.12.0-211.47.1.el10_2.aarch64
        kernel-modules-6.12.0-211.47.1.el10_2.aarch64
        kernel-modules-core-6.12.0-211.47.1.el10_2.aarch64
        ```
        """
        output = self.run_cli("--assumeno", "upgrade", must_succeed=True)

        section = None
        last_row = None
        rows: list[tuple[str | None, re.Match[str]]] = []
        installed_evr: dict[tuple[str, str], str] = {}
        for line in output.splitlines():
            if heading := self._SECTION_REGEXP.match(line):
                section = heading["section"]
            elif replacing := self._REPLACING_REGEXP.match(line):
                old = self._NEVRA_REGEXP.match(replacing["nevra"])
                # A row also replaces the packages it obsoletes, which carry
                # other names and are not an installed version of it.
                if last_row and old and old["name"] == last_row["name"]:
                    installed_evr[last_row["name"], last_row["arch"]] = old["evr"]
            elif row := self._ROW_REGEXP.match(line):
                last_row = self._NEVRA_REGEXP.match(row["nevra"])
                if last_row and section in ("Installing", "Upgrading"):
                    rows.append((section, last_row))

        unpaired = dict.fromkeys(
            new["name"]
            for _, new in rows
            if (new["name"], new["arch"]) not in installed_evr
        )
        if unpaired:
            listing = self.run_cli(
                "repoquery", "--installed", *unpaired, must_succeed=True
            )
            for match in self._NEVRA_REGEXP.finditer(listing):
                installed_evr[match["name"], match["arch"]] = match["evr"]

        for row_section, new in rows:
            installed_version = installed_evr.get((new["name"], new["arch"]))
            if row_section == "Installing" and installed_version is None:
                continue
            yield self.package(
                id=new["name"],
                installed_version=installed_version,
                latest_version=new["evr"],
                arch=new["arch"],
            )

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        ```{caution}
        `repoquery` matches package names only, never summaries. The match
        ignores case and also accepts a `name-version` form, so
        {meth}`meta_package_manager.manager.PackageManager.refiltered_search`
        refines the exact results.
        ```

        A repository can keep several builds of a package, and `repoquery`
        prints a row for each. Only the newest build is reported.

        ```{code-block} shell-session

        $ microdnf repoquery *xxd*
        xxd-2:9.1.083-9.el10_2.2.aarch64
        xxd-2:9.1.083-9.el10_2.3.aarch64
        xxd-2:9.1.083-9.el10_2.4.aarch64
        xxd-2:9.1.083-9.el10_2.7.aarch64
        xxd-2:9.1.083-9.el10_2.12.aarch64
        xxd-2:9.1.083-9.el10_2.20.aarch64
        ```

        ```{code-block} shell-session

        $ microdnf repoquery xxd
        xxd-2:9.1.083-9.el10_2.2.aarch64
        xxd-2:9.1.083-9.el10_2.3.aarch64
        xxd-2:9.1.083-9.el10_2.4.aarch64
        xxd-2:9.1.083-9.el10_2.7.aarch64
        xxd-2:9.1.083-9.el10_2.12.aarch64
        xxd-2:9.1.083-9.el10_2.20.aarch64
        ```
        """
        output = self.run_cli(
            "repoquery", query if exact else f"*{query}*", must_succeed=True
        )
        newest = {
            match["name"]: match["evr"] for match in self._NEVRA_REGEXP.finditer(output)
        }
        for package_id, evr in newest.items():
            yield self.package(id=package_id, latest_version=evr)

    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package, optionally pinned to a version.

        `microdnf` resolves `name-version` the way it resolves a bare name, so a
        pin joins the two with a dash. The epoch and the release are optional:
        a version without a release installs the newest build of that version.

        ```{code-block} shell-session

        $ sudo microdnf --assumeyes install tree
        ```

        ```{code-block} shell-session

        $ sudo microdnf --assumeyes install xxd-2:9.1.083-9.el10_2.3
        ```
        """
        spec = package_id if version is None else f"{package_id}-{version}"
        return self.run_cli("--assumeyes", "install", spec, sudo=True)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all outdated packages.

        ```{code-block} shell-session

        $ sudo microdnf --assumeyes upgrade
        ```
        """
        return self.build_cli("--assumeyes", "upgrade", sudo=True)

    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade one package, optionally to a version.

        The version joins the package ID the way it does for `install`.

        ```{code-block} shell-session

        $ sudo microdnf --assumeyes upgrade tree
        ```

        ```{code-block} shell-session

        $ sudo microdnf --assumeyes upgrade xxd-9.1.083-9.el10_2.12
        ```
        """
        spec = package_id if version is None else f"{package_id}-{version}"
        return self.build_cli("--assumeyes", "upgrade", spec, sudo=True)

    def remove(self, package_id: str) -> str:
        """Remove one package and one only.

        ```{code-block} shell-session

        $ sudo microdnf --assumeyes remove tree
        ```
        """
        return self.run_cli("--assumeyes", "remove", package_id, sudo=True)

    def sync(self) -> None:
        """Download fresh metadata for every enabled repository.

        ```{code-block} shell-session

        $ sudo microdnf makecache
        ```
        """
        self.run_cli("makecache", sudo=True)

    def cleanup_cache(self) -> None:
        """Remove the cached packages and repository metadata.

        ```{code-block} shell-session

        $ sudo microdnf clean all
        ```
        """
        self.run_cli("clean", "all", sudo=True)
