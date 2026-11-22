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
from pathlib import Path
from typing import ClassVar

from extra_platforms import LINUX_LIKE

from ..capabilities import search_capabilities, version_not_implemented
from ..execution import CLIError
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


OSTREE_BOOTED = Path("/run/ostree-booted")
"""Marker file that ostree creates when the host boots from an ostree deployment.

On a host installed from packages, the `rpm-ostree` binary can be present and
answer `--version`, but its daemon has no deployment to manage, so every verb
fails. This file is what tells the two hosts apart.
"""

UNCHANGED_EXIT_CODE = 77
"""Exit code of `rpm-ostree upgrade --check` when no update is available.

`--check` implies `--unchanged-exit-77`, so this code reports a status, not a
failure.
"""


class RPM_OSTree(PackageManager):
    """rpm-ostree, the hybrid image and package system of Fedora's ostree variants.

    Fedora IoT, the Fedora Atomic Desktops (Silverblue, Kinoite, ...) and Fedora
    CoreOS boot a read-only base image, on which `rpm-ostree` layers RPM
    packages. `dnf` cannot write to the read-only `/usr` of these hosts, so
    `rpm-ostree` is the only manager that reaches the packages of the Fedora
    repositories.

    `mpm` considers this manager available only on a host that booted from an
    ostree deployment, which `/run/ostree-booted` marks.

    Each install, removal and upgrade writes a new deployment, which becomes
    active at the next boot. Run `systemctl reboot` to switch to it. The
    `installed` listing reads the deployment that boots next, so a package shows
    there as soon as its install succeeds. To make an install active at once,
    add `--apply-live` to it:

    ```toml
    [mpm.overrides.rpm-ostree]
    operations.install.extra_args = ["--apply-live"]
    ```

    `upgrade --all` follows the ref of the deployment. On Fedora IoT, the
    `fedora/stable` ref moves to each new Fedora release, so an upgrade can
    move the host to the next major version. `rpm-ostree rollback` returns to
    the previous deployment.

    The daemon refuses every change, and the update check of `outdated`, from
    a user who is not root. `mpm` runs these commands with `sudo`.
    """

    operation_notes: ClassVar = {
        "installed": (
            "Lists the layered packages only: the packages of the base image are "
            "left out."
        ),
        "upgrade": (
            "Upgrades the base image and every layered package together: no verb "
            "upgrades one package."
        ),
    }

    name = "rpm-ostree"

    homepage_url = "https://coreos.github.io/rpm-ostree/"
    documentation_url = "https://coreos.github.io/rpm-ostree/administrator-handbook/"
    repository_url = "https://github.com/coreos/rpm-ostree"
    logo = "fedora"

    keywords = ("coreos", "silverblue")

    platforms = LINUX_LIKE

    default_sudo = True
    privileged_operations = frozenset(
        {"cleanup", "install", "outdated", "remove", "sync", "upgrade_all"},
    )

    requirement = ">=2023.6"
    """`2023.6` added the `search` verb.

    The other features this manager uses are older: `install --assumeyes`
    arrived in `2022.13`, and `--idempotent` in `2019.6`.
    """

    version_regexes = (r"Version: '(?P<version>[^']+)'",)
    """
    ```{code-block} shell-session

    $ rpm-ostree --version
    rpm-ostree:
     Version: '2026.3'
     Git: 937cd35dc42acb965b72e03f662cf4e19e770277
     Features:
      - rust
      - compose
      - container
      - fedora-integration
    ```
    """

    stderr_noise = re.compile(
        r"^Note: --check and --preview may be unreliable\.",
    )
    """The warning `upgrade --check` prints on each run.

    `--check` exits `77` when no update is available, and still prints this
    note. Declared as noise, it does not make that status read as a failure.
    """

    _NAME_VERSION_REGEXP = re.compile(
        r"^(?P<package_id>.+)-(?P<version>(?:\d+:)?[^-]+-[^-]+)$",
    )
    """Split `name-[epoch:]version-release`, the arch already removed.

    RPM forbids dashes in the version and release fields, so the last two
    dash-separated fields are the version and the release, whatever dashes the
    package name holds.
    """

    _SEARCH_REGEXP = re.compile(r"^(?P<package_id>\S+) : (?P<description>.*)$")
    """One search result: the package name, then its summary."""

    _NAME_MATCHED_SECTION = "===== Name Matched ====="
    """Header of the search section that lists the packages whose name matched."""

    @property
    def unavailable_reason(self) -> str | None:
        """Add the ostree boot to the conditions of the base class.

        See {data}`~meta_package_manager.managers.rpm_ostree.OSTREE_BOOTED` for
        why the binary alone is not enough.
        """
        reason = super().unavailable_reason
        if reason is None and not OSTREE_BOOTED.exists():
            return f"{OSTREE_BOOTED} is missing: the host did not boot from ostree"
        return reason

    def _parse_nevra(self, nevra: str) -> tuple[str, str | None, str | None]:
        """Split a `name-[epoch:]version-release.arch` string.

        Returns `(name, evr, arch)`. A string that does not split keeps its
        whole value as the name, with no version and no arch.
        """
        nevr, _, arch = nevra.rpartition(".")
        split = self.split_name_version(nevr) if nevr else None
        if not split:
            return nevra, None, None
        return split[0], split[1], arch

    def _layered_versions(
        self, checksum: str, names: list[str]
    ) -> dict[str, tuple[str, str]]:
        """Map each layered package name to its `(evr, arch)` in a deployment.

        The status of a deployment names its layered packages without their
        versions, so `mpm` reads them from the RPM database of its commit.

        ```{code-block} shell-session

        $ rpm-ostree db list f392b68304abf7f3e65f94efd6b5d19f430f7f13757f0de581d6276ef42516f6 nyancat
        ostree commit: f392b68304abf7f3e65f94efd6b5d19f430f7f13757f0de581d6276ef42516f6
         nyancat-1.5.2-19.fc45.aarch64
        ```
        """  # noqa: E501
        output = self.run_cli("db", "list", checksum, *names, auto_extra_args=False)
        versions = {}
        for line in output.splitlines():
            line = line.strip()
            if not line or line.startswith("ostree commit:"):
                continue
            name, evr, arch = self._parse_nevra(line)
            if evr and arch:
                versions[name] = (evr, arch)
        return versions

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch the layered packages of the deployment that boots next.

        `rpm-ostree` lists that deployment first. Its `packages` field holds the
        packages layered from the repositories, and its
        `requested-local-packages` field the NEVRA of each RPM file layered from
        the disk.

        ```{code-block} shell-session

        $ rpm-ostree status --jsonpath '$.deployments[0]'
        [
          {
            "unlocked" : "none",
            "base-local-replacements" : [],
            "requested-local-packages" : [],
            "base-commit-meta" : {
              "ostree.bootable" : true,
              "ostree.composefs.digest.v0" : [
                238,
                21,
                197,
                170,
                215,
                4,
                118,
                39,
                93,
                199,
                144,
                139,
                83,
                134,
                22,
                107,
                46,
                47,
                167,
                90,
                186,
                123,
                59,
                149,
                201,
                224,
                218,
                117,
                252,
                214,
                162,
                186
              ],
              "rpmostree.inputhash" : "c20f6bd494cc113df869766070443fed1221640f9b1777daf43f892d7f27a142",
              "version" : "45.20261118.0",
              "rpmostree.initramfs-args" : [
                "--no-hostonly",
                "--add",
                "ignition watchdog"
              ],
              "ostree.linux" : "7.3.4-300.fc45.aarch64",
              "rpmostree.rpmmd-repos" : [
                {
                  "id" : "repo-0",
                  "timestamp" : 7014605364523958272
                },
                {
                  "id" : "repo-1",
                  "timestamp" : 4000882475696914432
                },
                {
                  "id" : "repo-2",
                  "timestamp" : -4832935889971707904
                },
                {
                  "id" : "repo-3",
                  "timestamp" : -3893084345665060864
                }
              ]
            },
            "base-removals" : [],
            "gpg-enabled" : true,
            "pinned" : false,
            "osname" : "fedora-iot",
            "base-remote-replacements" : {    },
            "origin" : "fedora-iot:fedora/stable/aarch64/iot",
            "regenerate-initramfs" : false,
            "checksum" : "f392b68304abf7f3e65f94efd6b5d19f430f7f13757f0de581d6276ef42516f6",
            "requested-base-local-replacements" : [],
            "id" : "fedora-iot-f392b68304abf7f3e65f94efd6b5d19f430f7f13757f0de581d6276ef42516f6.0",
            "version" : "45.20261118.0",
            "base-version" : "45.20261118.0",
            "base-checksum" : "bb7e47ed47aaff673f8e9351c987e52006c93467a4b90060fad0a7b2c353f8c3",
            "requested-base-removals" : [],
            "requested-local-fileoverride-packages" : [],
            "serial" : 0,
            "base-timestamp" : 1794999966,
            "staged" : false,
            "booted" : true,
            "layered-commit-meta" : {
              "rpmostree.clientlayer" : true,
              "version" : "45.20261118.0",
              "rpmostree.clientlayer_version" : 6,
              "rpmostree.state-sha512" : "9594d534fb5df2931ad9708e92ff62aa59785dc20a9c858ba9b0b635c448de57f2f2d1a0f987e3da5635a2eb799afaea38c46b6e1d9cb89e4a24a9d33583b9ae",
              "rpmostree.rpmmd-repos" : [
                {
                  "id" : "fedora",
                  "timestamp" : 1793218657
                },
                {
                  "id" : "fedora-cisco-openh264",
                  "timestamp" : 1774349753
                },
                {
                  "id" : "updates",
                  "timestamp" : 1795309053
                }
              ],
              "ostree.linux" : "7.3.4-300.fc45.aarch64",
              "ostree.bootable" : true
            },
            "packages" : [
              "nyancat"
            ],
            "requested-packages" : [
              "nyancat"
            ],
            "timestamp" : 1795334884,
            "signatures" : [
              [
                true,
                false,
                false,
                false,
                false,
                "4F50A6114CD5C6976A7F1179655A4B02F577861E",
                1795000005,
                0,
                "RSA",
                "SHA256",
                "Fedora",
                "fedora-45-primary@fedoraproject.org",
                "4F50A6114CD5C6976A7F1179655A4B02F577861E",
                0,
                0
              ]
            ]
          }
        ]
        ```
        """  # noqa: E501
        output = self.run_cli(
            "status",
            "--jsonpath",
            "$.deployments[0]",
            must_succeed=True,
            auto_extra_args=True,
        )
        matches = json.loads(output) if output else []
        if not matches or not isinstance(matches[0], dict):
            return
        deployment = matches[0]

        names = deployment.get("packages") or []
        checksum = deployment.get("checksum")
        versions = (
            self._layered_versions(checksum, names)
            if names and isinstance(checksum, str)
            else {}
        )
        for package_id in names:
            evr, arch = versions.get(package_id, (None, None))
            yield self.package(id=package_id, installed_version=evr, arch=arch)

        for nevra in deployment.get("requested-local-packages") or []:
            package_id, evr, arch = self._parse_nevra(nevra)
            yield self.package(id=package_id, installed_version=evr, arch=arch)

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch the packages the next upgrade changes.

        `upgrade --check` refreshes the update that the daemon caches, then
        `status` reads its package diff. Each row of `upgraded` holds a type (`0`
        for the base image, `1` for a layered package), the package name, and
        the version and arch on each side. The base image is part of the list,
        because `upgrade --all` updates it with the layered packages.

        ```{code-block} shell-session

        $ sudo rpm-ostree upgrade --check
        2 metadata, 0 content objects fetched; 24 KiB transferred in 5 seconds; 0 bytes content written
        Receiving metadata objects: 1/(estimating) 148 bytes/s 592 bytes...done
        Enabled rpm-md repositories: fedora fedora-cisco-openh264 updates
        Updating metadata for 'fedora'...done
        Updating metadata for 'fedora-cisco-openh264'...done
        Updating metadata for 'updates'...done
        Importing rpm-md...done
        rpm-md repo 'fedora'; generated: 2026-10-28T20:17:37Z solvables: 66681
        rpm-md repo 'fedora-cisco-openh264'; generated: 2026-03-24T10:55:53Z solvables: 3
        rpm-md repo 'updates'; generated: 2026-11-22T00:57:33Z solvables: 11615
        AvailableUpdate:
                Version: 45.20261121.0 (2026-11-21T11:05:41Z)
                 Commit: 9282cc873b386fc0e61815760a55d0ec9aa46050ceb1c298c31600878d51e665
           GPGSignature: Valid signature by 4F50A6114CD5C6976A7F1179655A4B02F577861E
          SecAdvisories: 2 important
                   Diff: 3 upgraded
        ```

        ```{code-block} shell-session

        $ rpm-ostree status --jsonpath $.cached-update.rpm-diff.upgraded
        [
          [
            [
              0,
              "ignition",
              [
                "2.27.0-2.fc45",
                "aarch64"
              ],
              [
                "2.28.0-2.fc45",
                "aarch64"
              ]
            ],
            [
              0,
              "ignition-edge",
              [
                "2.27.0-2.fc45",
                "aarch64"
              ],
              [
                "2.28.0-2.fc45",
                "aarch64"
              ]
            ],
            [
              0,
              "sqlite-libs",
              [
                "3.53.4-1.fc45",
                "aarch64"
              ],
              [
                "3.54.1-2.fc45",
                "aarch64"
              ]
            ]
          ]
        ]
        ```

        ```{note}
        With no update available, `upgrade --check` prints
        `No updates available.` and exits `77`. Upstream warns that the check
        may be unreliable: it can report an update that `rpm-ostree upgrade`
        then does not apply
        ([coreos/rpm-ostree#1579](https://github.com/coreos/rpm-ostree/issues/1579)).
        ```
        """  # noqa: E501
        errors_before = len(self.cli_errors)
        try:
            self.run_cli("upgrade", "--check", sudo=True, auto_extra_args=True)
        except CLIError as error:
            # `mpm --stop-on-error` raises on any non-zero exit, the status of an
            # up-to-date host included.
            if error.code != UNCHANGED_EXIT_CODE:
                raise
            del self.cli_errors[errors_before:]
        # A failed check leaves the cached update of an earlier check in place,
        # which the status below would report as current.
        if len(self.cli_errors) > errors_before:
            return

        output = self.run_cli(
            "status",
            "--jsonpath",
            "$.cached-update.rpm-diff.upgraded",
            must_succeed=True,
            auto_extra_args=False,
        )
        matches = json.loads(output) if output else []
        if not matches:
            return
        for _type, package_id, (old_evr, _old_arch), (new_evr, new_arch) in matches[0]:
            yield self.package(
                id=package_id,
                installed_version=old_evr,
                latest_version=new_evr,
                arch=new_arch,
            )

    @search_capabilities(extended_support=True, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        `rpm-ostree search` matches the query against package names and
        summaries, and prints one section per kind of match. A package that
        matches both appears in each section. The search does not report
        versions.

        ```{code-block} shell-session

        $ rpm-ostree search nyan

        ===== Summary & Name Matched =====
        hanyang-gothic-a1-fonts : HanYang Gothic A1, an elegant Korean and Latin font
        nyancat : Nyancat rendered in your terminal

        ===== Name Matched =====
        hanyang-gothic-a1-fonts : HanYang Gothic A1, an elegant Korean and Latin font
        nyancat : Nyancat rendered in your terminal

        ===== Summary Matched =====
        hanyang-gothic-a1-fonts : HanYang Gothic A1, an elegant Korean and Latin font
        nyancat : Nyancat rendered in your terminal
        ```
        """
        output = self.run_cli("search", query)

        section = None
        seen = set()
        for line in output.splitlines():
            if line.startswith("====="):
                section = line.strip()
                continue
            if not extended and section != self._NAME_MATCHED_SECTION:
                continue
            match = self._SEARCH_REGEXP.match(line)
            if not match or match["package_id"] in seen:
                continue
            seen.add(match["package_id"])
            yield self.package(id=match["package_id"], description=match["description"])

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Layer one package.

        `--assumeyes` answers the confirmation that `--apply-live` asks for on a
        terminal.

        ```{code-block} shell-session

        $ sudo rpm-ostree install --idempotent --assumeyes nyancat
        ```
        """
        return self.run_cli(
            "install", "--idempotent", "--assumeyes", package_id, sudo=True
        )

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade the base image and the layered packages.

        ```{code-block} shell-session

        $ sudo rpm-ostree upgrade
        ```
        """
        return self.build_cli("upgrade", sudo=True)

    def remove(self, package_id: str) -> str:
        """Remove one layered package.

        ```{code-block} shell-session

        $ sudo rpm-ostree uninstall --idempotent nyancat
        ```
        """
        return self.run_cli("uninstall", "--idempotent", package_id, sudo=True)

    def sync(self) -> None:
        """Refresh the cached metadata of the RPM repositories.

        ```{code-block} shell-session

        $ sudo rpm-ostree refresh-md
        ```
        """
        self.run_cli("refresh-md", sudo=True)

    def cleanup_cache(self) -> None:
        """Delete the cached metadata of the RPM repositories.

        ```{code-block} shell-session

        $ sudo rpm-ostree cleanup --repomd
        ```
        """
        self.run_cli("cleanup", "--repomd", sudo=True)
