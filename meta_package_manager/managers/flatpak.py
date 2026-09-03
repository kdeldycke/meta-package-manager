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
from datetime import datetime

from extra_platforms import UNIX_WITHOUT_MACOS

from ..capabilities import search_capabilities, version_not_implemented
from ..execution import CLIError
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class Flatpak(PackageManager):
    """Flatpak manages sandboxed desktop applications pulled from remotes like
    Flathub.

    mpm covers applications only: every listing passes `--app`, so runtimes
    and SDKs stay out of scope. Listings are requested with
    `--columns=name,application,version --ostree-verbose` and parsed as
    tab-separated rows.

    ```{note}
    All operations target the system-wide scope except `cleanup` which only
    repairs the user installation. Per-scope targeting (system vs user) is
    tracked in [#1725](https://github.com/kdeldycke/meta-package-manager/issues/1725).
    ```

    ```{note}
    Escalation is polkit's job, so no operation is marked `sudo`: flatpak
    hands system-scope mutations to its privileged system helper over D-Bus,
    which authorizes them through polkit (Flathub documents plain
    `flatpak install`). Under a strict polkit policy, unattended mutations
    need a rule permitting them without interactive authentication.
    ```

    ```{caution}
    `outdated` reads each pending update's latest version from
    `remote-ls --updates`, then runs one `flatpak info` per package to
    recover its installed version: a follow-up CLI call for every outdated
    app.
    ```

    ```{note}
    A `--brewfile` dump emits the bare `flatpak "id"` form, mpm capturing no
    origin remote per app. See {doc}`/dump`, section "Flatpak remote".
    ```
    """

    homepage_url = "https://flatpak.org"
    logo = "flatpak"

    keywords = ("flathub",)

    brewfile_entry_type = "flatpak"
    """Mapped to Homebrew Bundle's `flatpak` extension.

    Its `with: ["remote"]` keyword goes unused, {meth}`installed` capturing no
    origin remote to fill it with. See {doc}`/dump`, section "Flatpak remote".
    """

    platforms = UNIX_WITHOUT_MACOS

    requirement = ">=1.2.0"

    _LIST_REGEXP = re.compile(
        r"(?P<name>.+?)\t(?P<package_id>\S+)\t?(?P<latest_version>.*)",
    )
    _SEARCH_REGEXP = re.compile(
        r"""
        ^(?P<package_name>\S+)\t
        (?P<description>.+)\t
        (?P<package_id>\S+)\t
        (?P<version>\S+)\t
        (?P<branch>\S+)\t
        (?P<remotes>.+)
        """,
        # Walked over the whole output by `findall`, so `^` has to bind to each
        # line: without this only the first result is ever matched.
        re.VERBOSE | re.MULTILINE,
    )
    _ORIGIN_REGEXP = re.compile(r"^\s*Origin:\s*(?P<remote>\S+)", re.MULTILINE)
    _REMOTE_DATE_REGEXP = re.compile(
        r"^\s*Date:\s*(?P<date>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4})",
        re.MULTILINE,
    )
    _C_LOCALE_ENV = {"LC_ALL": "C.UTF-8"}
    """Locale forced on the release-date probes below.

    The `Origin:` and `Date:` field labels parsed by {meth}`release_date` are
    localized by flatpak, and the probes key on their English spelling.
    """

    version_regexes = (r"Flatpak\s+(?P<version>\S+)",)
    """
    ```{code-block} shell-session

    $ flatpak --version
    Flatpak 1.4.2
    ```
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        ```{code-block} shell-session

        $ flatpak list --app --columns=name,application,version \
        > --ostree-verbose
        Peek	com.uploadedlobster.peek	1.3.1
        Fragments	de.haeckerfelix.Fragments	1.4
        GNOME MPV	io.github.GnomeMpv	0.16
        Syncthing GTK	me.kozec.syncthingtk	v0.9.4.3
        Builder	org.flatpak.Builder
        ```
        """
        output = self.run_cli(
            "list",
            "--app",
            "--columns=name,application,version",
            "--ostree-verbose",
        )

        for package in output.splitlines():
            match = self._LIST_REGEXP.match(package)
            if match:
                name, package_id, installed_version = match.groups()
                yield self.package(
                    id=package_id,
                    name=name,
                    installed_version=installed_version,
                )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        ```{code-block} shell-session

        $ flatpak remote-ls --app --updates --columns=name,application,version \
            --ostree-verbose
        GNOME Dictionary	org.gnome.Dictionary	3.26.0
        Files	org.gnome.Nautilus	42.2
        ```
        """
        output = self.run_cli(
            "remote-ls",
            "--app",
            "--updates",
            "--columns=name,application,version",
            "--ostree-verbose",
        )

        for package in output.splitlines():
            match = self._LIST_REGEXP.match(package)
            if match:
                name, package_id, latest_version = match.groups()

                info_installed_output = self.run_cli(
                    "info",
                    "--ostree-verbose",
                    package_id,
                )

                current_version = re.search(
                    r"version:\s(?P<version>\S.*?)\n",
                    info_installed_output,
                    re.IGNORECASE,
                )

                installed_version = (
                    current_version.group("version") if current_version else None
                )

                yield self.package(
                    id=package_id,
                    name=name,
                    latest_version=latest_version,
                    installed_version=installed_version,
                )

    def release_date(self, package_id: str) -> datetime | None:
        """Publication timestamp of the latest build of an app, read off its remote.

        The date is the ostree commit timestamp of the newest commit on the
        app's branch, reported by `flatpak remote-info` and rendered in UTC
        with a literal `+0000` offset whatever the host locale. The remote's
        build service stamps it at publication (Flathub's buildbot for the
        `flathub` remote), so the app's author cannot backdate it, which is
        what makes it a sound cooldown clock. On a third-party remote the
        publisher stamps it instead: the probe is then only as trustworthy as
        the remote itself, exactly like the packages it serves.

        The probe resolves the remote to interrogate from the installed app's
        origin, and falls back to trying every configured remote for an app
        not installed yet (an `install` gated before its first installation).
        On a host with several remotes, that fallback logs one error per
        remote not serving the app.

        ```{code-block} console

        $ flatpak remote-info --ostree-verbose flathub org.gnome.Calculator

        Calculator - Perform arithmetic, scientific or financial calculations

                    ID: org.gnome.Calculator
                   Ref: app/org.gnome.Calculator/aarch64/stable
                  Arch: aarch64
                Branch: stable
               Version: 50.0
               License: GPL-3.0-or-later
            Collection: org.flathub.Stable
         Download Size: 1.8 MB
        Installed Size: 4.9 MB
               Runtime: org.gnome.Platform/aarch64/50
                   Sdk: org.gnome.Sdk/aarch64/50

                Commit: 473c4d6d2d553eaeba13c0f1fd27cc9af0c4362cb4ad2a7050149930e89f3eb1
                Parent: 6f12ad4cd67efce88bf63ec51c13a9b6a1891c61d8ab640b85ce25d0f37f089c
               Subject: Merge pull request #52 from flathub/update-master-19cd934 (ee57e22e7a51)
                  Date: 2026-03-18 19:40:01 +0000
        ```
        """
        remotes = []
        if package_id in self.installed_ids:
            origin_output = self.run_cli(
                "info",
                "--ostree-verbose",
                package_id,
                override_extra_env=self._C_LOCALE_ENV,
            )
            origin = self._ORIGIN_REGEXP.search(origin_output)
            if origin:
                remotes.append(origin.group("remote"))
        if not remotes:
            remotes = self.run_cli(
                "remotes",
                "--columns=name",
                "--ostree-verbose",
                override_extra_env=self._C_LOCALE_ENV,
            ).split()
        for remote in remotes:
            try:
                output = self.run_cli(
                    "remote-info",
                    "--ostree-verbose",
                    remote,
                    package_id,
                    override_extra_env=self._C_LOCALE_ENV,
                )
            except CLIError:
                # The app is not served by this remote: try the next one.
                continue
            match = self._REMOTE_DATE_REGEXP.search(output)
            if match:
                return datetime.strptime(
                    match.group("date"), "%Y-%m-%d %H:%M:%S %z"
                )
        return None

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

        $ flatpak search gitg --ostree-verbose
        gitg    GUI for git        org.gnome.gitg  3.32.1  stable  flathub
        ```
        """
        output = self.run_cli("search", query, "--ostree-verbose")

        for (
            package_name,
            description,
            package_id,
            version,
            _branch,
            _remotes,
        ) in self._SEARCH_REGEXP.findall(output):
            yield self.package(
                id=package_id,
                name=package_name,
                description=description,
                latest_version=version,
            )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        ```{code-block} shell-session

        $ flatpak install --noninteractive org.gnome.Dictionary
        ```
        """
        return self.run_cli("install", "--noninteractive", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all outdated packages.

        ```{code-block} shell-session

        $ flatpak update --noninteractive
        ```
        """
        return self.build_cli("update", "--noninteractive")

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the provided package.

        ```{code-block} shell-session

        $ flatpak update --noninteractive org.gnome.Dictionary
        ```
        """
        return self.build_cli("update", "--noninteractive", package_id)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        ```{code-block} shell-session

        $ flatpak uninstall --noninteractive org.gnome.Dictionary
        ```
        """
        return self.run_cli("uninstall", "--noninteractive", package_id)

    def cleanup_orphan(self) -> None:
        """Uninstall runtimes and extensions no longer used by any installed app.

        ```{code-block} shell-session

        $ flatpak uninstall --unused --noninteractive
        ```
        """
        self.run_cli("uninstall", "--unused", "--noninteractive")

    def cleanup_repair(self) -> None:
        """Verify and repair the per-user installation.

        See the [`flatpak repair` reference](https://docs.flatpak.org/en/latest/flatpak-command-reference.html#flatpak-repair).

        ```{code-block} shell-session

        $ flatpak repair --user
        ```
        """
        self.run_cli("repair", "--user")

    def doctor_cli(self) -> tuple[str, ...]:
        """Generates the CLI running the native self-diagnosis.

        The read-only twin of {meth}`cleanup_repair`: `--dry-run` reports
        what a repair of the per-user installation would fix without touching it.

        ```{code-block} shell-session

        $ flatpak repair --user --dry-run
        ```
        """
        return self.build_cli("repair", "--user", "--dry-run")
