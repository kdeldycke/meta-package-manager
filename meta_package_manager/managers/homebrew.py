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
import logging
import re
from functools import cached_property
from operator import methodcaller
from pathlib import Path
from typing import ClassVar

from extra_platforms import LINUX_LIKE, MACOS

from ..capabilities import version_not_implemented
from ..manager import PackageManager
from ..package import (
    EMPTY_METADATA,
    Checksum,
    ChecksumAlgorithm,
    Dependency,
    DependencyScope,
    PackageMetadata,
    Supplier,
)
from ..version import parse_version

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from ..package import Package


class Homebrew(PackageManager):
    """Virtual base shared by the :py:class:`Brew` and :py:class:`Cask` managers.

    Homebrew is the umbrella project behind the ``brew`` CLI. mpm exposes it as
    two managers over that single binary: :py:class:`Brew` for formulae built
    from recipes, and :py:class:`Cask` for pre-built macOS applications, each
    pinning its half with a ``--formula`` or ``--cask`` selector. This base
    holds the shared query, mutation and metadata logic; the concrete classes
    carry the manager-level narrative.
    """

    platforms = LINUX_LIKE, MACOS
    """Homebrew core is now compatible with `Linux and Windows Subsystem for Linux (WSL)
    2 <https://docs.brew.sh/Homebrew-on-Linux>`_."""

    requirement = ">=6.0.0"
    """Vanilla ``brew`` and ``cask`` CLIs now shares the same version.

    `2.7.0 <https://github.com/Homebrew/brew/releases/tag/2.7.0>`_ was the first release
    to enforce the use of ``--cask`` option.

    `6.0.0 <https://github.com/Homebrew/brew/releases/tag/6.0.0>`_ is the first
    release in which ask mode is the default for ``brew install`` and ``brew upgrade``,
    and the first to ship the ``--yes`` opt-out flag that mpm relies on for
    non-interactive upgrades.
    """

    # Declare this manager as virtual, i.e. not tied to a real CLI.
    virtual = True

    extra_env: ClassVar = {
        # Disable analytics.
        "HOMEBREW_NO_ANALYTICS": "1",
        # Disable configuration hints to reduce verbosity.
        "HOMEBREW_NO_ENV_HINTS": "1",
        # Do not let brew mix the update operation with others. Mpm has a separate
        # "sync" command for that. This silo-ed behavior has been requested by user
        # since the beginning of mpm:
        # https://github.com/kdeldycke/meta-package-manager/issues/36
        "HOMEBREW_NO_AUTO_UPDATE": "1",
        # See: https://docs.brew.sh/FAQ#why-cant-i-open-a-mac-app-from-an-unidentified-developer
        # "HOMEBREW_CASK_OPTS": "--no-quarantine",
    }

    _INSTALLED_REGEXP = re.compile(
        r"""
        (?P<package_id>\S+)     # Any non-empty characters.
        (?P<removed> \(!\))?    # Package removed flag.
        \                       # A space.
        (?P<versions>.+)        # Versions.
        """,
        re.VERBOSE,
    )
    _SEARCH_DESC_REGEXP = re.compile(
        r"""
        (?:==>\s\S+\s)?           # Ignore section starting with '==>'.
        (?P<package_id>\S+)       # Any non-empty characters.
        :                         # Semi-colon.
        (                         # Optional group start (ignored below with _).
            \s+                   # Blank characters.
            \(                    # Opening parenthesis.
            (?P<package_name>.+)  # Any string.
            \)                    # Closing parenthesis.
        )?                        # Optional group end.
        \s+                       # Blank characters.
        (?P<description>.+)       # Any string.
        """,
        re.VERBOSE,
    )
    _SEARCH_REGEXP = re.compile(
        r"""
        (?:==>\s\S+\s)?           # Ignore section starting with '==>'.
        (?P<package_id>[^\s✔]+)   # Anything not a whitespace or ✔.
        """,
        re.VERBOSE,
    )

    version_regexes = (r"Homebrew\s+(?P<version>\S+)",)
    """
    .. code-block:: shell-session

        $ brew --version
        Homebrew 1.8.6-124-g6cd4c31
        Homebrew/homebrew-core (git revision 533d; last commit 2018-12-28)
        Homebrew/homebrew-cask (git revision 5095b; last commit 2018-12-28)
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            $ brew list --versions --formula
            ack 2.14
            apg 2.2.3
            audacity (!) 2.1.2
            apple-gcc42 4.2.1-5666.3
            atk 2.22.0
            bash 4.4.5
            bash-completion 1.3_1
            boost 1.63.0
            c-ares 1.12.0
            graphviz 2.40.1 2.40.20161221.0239
            quicklook-json latest

        .. code-block:: shell-session

            $ brew list --versions --cask
            aerial 1.2beta5
            android-file-transfer latest
            audacity (!) 2.1.2
            firefox 49.0.1
            flux 37.7
            gimp 2.8.18-x86_64
            java 1.8.0_112-b16
            tunnelblick 3.6.8_build_4625 3.6.9_build_4685
            virtualbox 5.1.8-111374 5.1.10-112026

        .. todo::

            Use the ``removed`` variable to detect removed packages (which are
            reported with a ``(!)`` flag). See:
            https://github.com/caskroom/homebrew-cask/blob/master/doc
            /reporting_bugs/uninstall_wrongly_reports_cask_as_not_installed.md
            and https://github.com/kdeldycke/meta-package-manager/issues/17 .
        """
        output = self.run_cli("list", "--quiet", "--versions")

        for package_id, _removed, versions in map(
            methodcaller("groups"),
            self._INSTALLED_REGEXP.finditer(output),
        ):
            # Keep highest version found.
            version = max(map(parse_version, versions.split()))
            yield self.package(id=package_id, installed_version=version)

    @cached_property
    def _brew_prefix(self) -> Path | None:
        """Resolve ``brew --prefix`` once.

        Used to locate per-formula ``<prefix>/Cellar/<formula>/<version>``
        directories where Homebrew writes ``sbom.spdx.json`` when
        installed under ``HOMEBREW_SBOM=1``. Returns ``None`` if the
        prefix cannot be determined, in which case the extractor falls
        back to API-only metadata.
        """
        try:
            output = self.run_cli(
                "--prefix",
                auto_post_args=False,
                must_succeed=True,
            )
        except Exception:  # noqa: BLE001
            return None
        prefix = output.strip()
        return Path(prefix) if prefix else None

    def package_metadata_batch(
        self,
        packages: Iterable[Package],
    ) -> Iterator[tuple[Package, PackageMetadata]]:
        """Enrich installed packages with Homebrew's API + per-formula data.

        Runs ``brew info --json=v2 --installed`` in a single shell-out and
        joins the result back onto the inventory list by package ID. For
        each formula that has ``<prefix>/Cellar/<name>/<version>/sbom.spdx.json``
        on disk (the file Homebrew writes when installed under
        ``HOMEBREW_SBOM=1``), the metadata's ``external_sbom_path`` points
        at it so the SPDX renderer can splice the upstream document into
        the aggregate.

        Casks reuse the same JSON payload through the ``casks`` array but
        do not get the SBOM-file treatment (Homebrew does not emit one
        for casks).
        """
        package_list = list(packages)
        if not package_list:
            return

        try:
            output = self.run_cli("info", "--json=v2", "--installed", must_succeed=True)
        except Exception as exc:  # noqa: BLE001
            # If the bulk query fails, fall back to empty metadata for
            # every package; the renderer will emit minimal entries.
            logging.debug(f"brew info --json=v2 --installed failed: {exc}")
            for package in package_list:
                yield package, EMPTY_METADATA
            return

        try:
            payload = json.loads(output) if output else {}
        except json.JSONDecodeError as exc:
            logging.debug(f"brew info JSON decode failed: {exc}")
            for package in package_list:
                yield package, EMPTY_METADATA
            return

        formulae_by_name: dict[str, dict] = {}
        for formula in payload.get("formulae") or ():
            formulae_by_name[formula.get("name", "")] = formula
            for alias in formula.get("aliases") or ():
                formulae_by_name.setdefault(alias, formula)
            for old_name in formula.get("oldnames") or ():
                formulae_by_name.setdefault(old_name, formula)
            full_name = formula.get("full_name")
            if full_name:
                formulae_by_name.setdefault(full_name, formula)

        casks_by_token: dict[str, dict] = {}
        for cask in payload.get("casks") or ():
            casks_by_token[cask.get("token", "")] = cask
            full_token = cask.get("full_token")
            if full_token:
                casks_by_token.setdefault(full_token, cask)

        for package in package_list:
            formula = formulae_by_name.get(package.id)
            cask = casks_by_token.get(package.id) if not formula else None
            if formula:
                yield package, self._formula_metadata(formula)
            elif cask:
                yield package, self._cask_metadata(cask)
            else:
                yield package, EMPTY_METADATA

    def _formula_metadata(self, formula: dict) -> PackageMetadata:
        """Map one entry from ``brew info --json=v2``'s ``formulae`` array
        into the portable :py:class:`PackageMetadata`.
        """
        installed_entries = formula.get("installed") or ()
        installed = installed_entries[-1] if installed_entries else {}

        deps: list[Dependency] = [
            Dependency(target_id=dep_name, scope=DependencyScope.RUNTIME)
            for dep_name in formula.get("dependencies") or ()
        ]
        deps.extend(
            Dependency(target_id=dep_name, scope=DependencyScope.BUILD)
            for dep_name in formula.get("build_dependencies") or ()
        )
        deps.extend(
            Dependency(target_id=dep_name, scope=DependencyScope.TEST)
            for dep_name in formula.get("test_dependencies") or ()
        )
        deps.extend(
            Dependency(target_id=dep_name, scope=DependencyScope.OPTIONAL)
            for dep_name in formula.get("optional_dependencies") or ()
        )
        deps.extend(
            Dependency(target_id=dep_name, scope=DependencyScope.RECOMMENDED)
            for dep_name in formula.get("recommended_dependencies") or ()
        )

        checksums: list[Checksum] = []
        # The bottle entry for the current platform carries a SHA256.
        bottle_files = ((formula.get("bottle") or {}).get("stable") or {}).get(
            "files"
        ) or {}
        for platform_payload in bottle_files.values():
            sha = (
                platform_payload.get("sha256")
                if isinstance(platform_payload, dict)
                else None
            )
            if sha:
                checksums.append(Checksum(ChecksumAlgorithm.SHA256, sha))
                break

        license_str = formula.get("license")

        download_url = ((formula.get("urls") or {}).get("stable") or {}).get("url")

        external_sbom_path = self._sbom_path_for_formula(
            formula.get("name"),
            installed.get("version") or formula.get("versions", {}).get("stable"),
        )

        tap = formula.get("tap")
        extras: dict[str, object] = {}
        if tap:
            extras["brew.tap"] = tap
        if installed.get("installed_on_request") is not None:
            extras["brew.installed_on_request"] = installed["installed_on_request"]
        if installed.get("poured_from_bottle") is not None:
            extras["brew.poured_from_bottle"] = installed["poured_from_bottle"]
        if formula.get("keg_only"):
            extras["brew.keg_only"] = True
            kor = formula.get("keg_only_reason") or {}
            if kor.get("reason"):
                extras["brew.keg_only_reason"] = kor["reason"]

        return PackageMetadata(
            download_url=download_url,
            homepage=formula.get("homepage"),
            license_declared=license_str,
            license_concluded=license_str,
            supplier=Supplier(name="Homebrew Formulae", url="https://brew.sh"),
            description=formula.get("desc"),
            summary=formula.get("desc"),
            dependencies=tuple(deps),
            checksums=tuple(checksums),
            external_sbom_path=external_sbom_path,
            extras=extras,
        )

    def _cask_metadata(self, cask: dict) -> PackageMetadata:
        """Map one entry from ``brew info --json=v2``'s ``casks`` array.

        Casks expose a leaner schema than formulae: no transitive
        dependency closure, a single ``url`` and ``sha256`` for the
        download, and a ``depends_on`` map limited to cross-cask edges.
        """
        depends_on = cask.get("depends_on") or {}
        deps: list[Dependency] = [
            Dependency(target_id=cask_dep, scope=DependencyScope.RUNTIME)
            for cask_dep in depends_on.get("cask") or ()
        ]
        deps.extend(
            Dependency(target_id=formula_dep, scope=DependencyScope.RUNTIME)
            for formula_dep in depends_on.get("formula") or ()
        )

        checksums: list[Checksum] = []
        sha = cask.get("sha256")
        if sha and sha != "no_check":
            checksums.append(Checksum(ChecksumAlgorithm.SHA256, sha))

        tap = cask.get("tap")
        extras: dict[str, object] = {}
        if tap:
            extras["brew.tap"] = tap
        if cask.get("auto_updates") is not None:
            extras["brew.auto_updates"] = cask["auto_updates"]

        return PackageMetadata(
            download_url=cask.get("url"),
            homepage=cask.get("homepage"),
            supplier=Supplier(
                name="Homebrew Cask",
                url="https://github.com/Homebrew/homebrew-cask",
            ),
            description=cask.get("desc"),
            summary=cask.get("name", [None])[0]
            if isinstance(cask.get("name"), list)
            else cask.get("name"),
            dependencies=tuple(deps),
            checksums=tuple(checksums),
            extras=extras,
        )

    def _sbom_path_for_formula(
        self, formula_name: str | None, version: str | None
    ) -> Path | None:
        """Locate ``<prefix>/Cellar/<formula>/<version>/sbom.spdx.json``.

        Returns ``None`` if the brew prefix is unknown or the file does
        not exist: that branch covers users who never set
        ``HOMEBREW_SBOM=1`` at install time, formulae installed before
        ``5.2.0`` introduced the flag, and casks.
        """
        if not formula_name or not version:
            return None
        prefix = self._brew_prefix
        if not prefix:
            return None
        candidate = prefix / "Cellar" / formula_name / str(version) / "sbom.spdx.json"
        return candidate if candidate.is_file() else None

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            $ brew outdated --json=v2 --formula | jq
            {
              "formulae": [
                {
                  "name": "pygobject3",
                  "installed_versions": [
                    "3.36.1"
                  ],
                  "current_version": "3.38.0",
                  "pinned": false,
                  "pinned_version": null
                },
                {
                  "name": "rav1e",
                  "installed_versions": [
                    "0.3.3"
                  ],
                  "current_version": "0.3.4",
                  "pinned": false,
                  "pinned_version": null
                }
              ],
              "casks": []
            }

        .. code-block:: shell-session

            $ brew outdated --json=v2 --cask | jq
            {
              "formulae": [],
              "casks": [
                {
                  "name": "electrum",
                  "installed_versions": "4.0.2",
                  "current_version": "4.0.3"
                },
                {
                  "name": "qlcolorcode",
                  "installed_versions": "3.0.2",
                  "current_version": "3.1.1"
                }
              ]
            }

        .. code-block:: shell-session

            $ brew outdated --json=v2 --greedy --cask | jq
            {
              "formulae": [],
              "casks": [
                {
                  "name": "amethyst",
                  "installed_versions": "0.14.3",
                  "current_version": "0.15.3"
                },
                {
                  "name": "balenaetcher",
                  "installed_versions": "1.5.106",
                  "current_version": "1.5.108"
                },
                {
                  "name": "caldigit-thunderbolt-charging",
                  "installed_versions": "latest",
                  "current_version": "latest"
                },
                {
                  "name": "electrum",
                  "installed_versions": "4.0.2",
                  "current_version": "4.0.3"
                },
                {
                  "name": "lg-onscreen-control",
                  "installed_versions": "5.33,cV8xqv5TSZA.upgrading, 5.47,yi5XuIZw6hg",
                  "current_version": "5.48,uYXSwyUCNFBbSch9PFw"
                }
              ]
            }

        .. note::

            Both the formula and cask payloads also carry ``pinned`` and
            ``pinned_version`` fields. The formula payload has always emitted them;
            the cask payload has emitted them since at least ``5.1.15`` but they only
            became meaningful with Homebrew
            `6.0.0 <https://brew.sh/2026/06/11/homebrew-6.0.0/>`_, which added
            `brew pin <cask> <https://github.com/Homebrew/brew/pull/22276>`_ so casks
            can now actually be pinned. ``mpm`` discards both fields today: pinned
            packages still appear in ``mpm outdated`` output, and ``brew upgrade``
            silently skips them at upgrade time. Track this gap if a future ``mpm``
            release wants to surface or filter on pin state.
        """
        # Build up the list of CLI options.
        options = ["--json=v2"]
        # Includes auto-update packages or not.
        if not self.ignore_auto_updates:
            options.append("--greedy")

        # List available updates. Do not use --quiet here: brew treats --quiet
        # and --json as mutually exclusive. See:
        # https://github.com/kdeldycke/meta-package-manager/issues/1703
        output = self.run_cli("outdated", options, must_succeed=True)

        package_list = self.parse_json(output)
        if package_list:
            for pkg_info in package_list["formulae"] + package_list["casks"]:
                # Interpret installed versions.
                versions = pkg_info["installed_versions"]
                if isinstance(versions, str):
                    versions = versions.split(", ")
                installed_version = max(map(parse_version, versions))

                latest_version = parse_version(pkg_info["current_version"])

                yield self.package(
                    id=pkg_info["name"],
                    installed_version=installed_version,
                    latest_version=latest_version,
                )

    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. caution::
            Search does not supports extended mode.

        .. code-block:: shell-session

            $ brew search sed
            ==> Formulae
            gnu-sed ✔                    libxdg-basedir
            ==> Casks
            eclipse-dsl                       marsedit
            focused                           physicseditor
            google-adwords-editor             prefs-editor
            licensed                          subclassed-mnemosyne

        .. code-block:: shell-session

            $ brew search sed --formulae
            ==> Formulae
            gnu-sed ✔                    libxdg-basedir

        .. code-block:: shell-session

            $ brew search sed --cask
            ==> Casks
            eclipse-dsl                       marsedit
            focused                           physicseditor
            google-adwords-editor             prefs-editor
            licensed                          subclassed-mnemosyne

        .. code-block:: shell-session

            $ brew search python --formulae
            ==> Formulae
            app-engine-python   boost-python3   python ✔          python-yq
            boost-python        gst-python      python-markdown   python@3.8 ✔

        .. code-block:: shell-session

            $ brew search "/^ssed$/" --formulae
            ==> Formulae
            ssed

        .. code-block:: shell-session

            $ brew search "/^sed$/" --formulae
            Error: No formula or cask found for "/^sed$/".

        .. code-block:: shell-session

            $ brew search tetris --formulae --desc
            ==> Formulae
            bastet: Bastard Tetris
            netris: Networked variant of tetris
            vitetris: Terminal-based Tetris clone
            yetris: Customizable Tetris for the terminal

        .. code-block:: shell-session

            $ brew search tetris --cask --desc
            ==> Casks
            not-tetris: (Not Tetris) [no description]
            tetrio: (TETR.IO) Free-to-play Tetris clone

        More doc at: https://docs.brew.sh/Manpage#search
        """
        # Keep track of package IDs already matched by the first extended search pass.
        matched_ids = set()

        # Additional search on description only.
        if extended:
            output = self.run_cli("search", "--quiet", query, "--desc")

            for (
                package_id,
                _,
                package_name,
                description,
            ) in self._SEARCH_DESC_REGEXP.findall(output):
                matched_ids.add(package_id)
                pkg = self.package(id=package_id, name=package_name)
                if description != "[no description]":
                    pkg.description = description
                yield pkg

        # Use regexp if exact match is requested.
        if exact:
            query = f"/^{query}$/"

        output = self.run_cli("search", "--quiet", query)

        for package_id in self._SEARCH_REGEXP.findall(output):
            # Deduplicate search results.
            if package_id not in matched_ids:
                yield self.package(id=package_id)

    def trust_tap(self, package_id: str) -> None:
        """Trust the tap a third-party ``package_id`` belongs to.

        Homebrew `6.0.0 <https://brew.sh/2026/06/11/homebrew-6.0.0/>`_ rejects code
        from third-party taps until the tap (or each formula or cask) has been
        explicitly trusted. Vanilla ``brew install`` would otherwise abort with a
        ``tap trust is required`` warning when the snapshot pins a
        ``user/tap/name`` package.

        Only fully-qualified package IDs (``user/tap/name``) need this step:
        core formulae and casks live on the trusted ``homebrew/core`` and
        ``homebrew/cask`` taps. The tap itself is registered first (idempotent
        if already tapped) so ``brew trust`` can resolve the formula or cask.
        The ``--formula`` and ``--cask`` flag is supplied by the subclass's
        :py:attr:`post_args`.

        .. code-block:: shell-session

            $ brew tap gromgit/fuse
            $ brew trust gromgit/fuse/ntfs-3g-mac --formula
        """
        if package_id.count("/") != 2:
            return
        user, tap, _ = package_id.split("/", 2)
        self.run_cli("tap", f"{user}/{tap}", auto_post_args=False)
        self.run_cli("trust", package_id)

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        Tap-qualified IDs (``user/tap/name``) are routed through
        :py:meth:`trust_tap` first so the install isn't rejected by Homebrew
        6.0.0's tap-trust gate.

        .. code-block:: shell-session

            $ brew install jpeginfo --formula
            ==> Downloading https://ghcr.io/core/jpeginfo/manifests/1.6.1_1-1
            ############################################################## 100.0%
            ==> Downloading https://ghcr.io/core/jpeginfo/blobs/sha256:27bb35884368b83
            ==> Downloading from https://pkg.githubcontent.com/ghcr1/blobs/sha256:27bb3
            ############################################################## 100.0%
            ==> Pouring jpeginfo--1.6.1_1.big_sure.bottle.1.tar.gz
            🍺  /usr/local/Cellar/jpeginfo/1.6.1_1: 7 files, 77.6KB

        .. code-block:: shell-session

            $ brew install pngyu --cask
            ==> Downloading https://nukesaq.github.io/Pngyu/download/Pngyu_mac_101.zip
            ################################################################## 100.0%
            ==> Installing Cask pngyu
            ==> Moving App 'Pngyu.app' to '/Applications/Pngyu.app'
            🍺  pngyu was successfully installed!
        """
        self.trust_tap(package_id)
        return self.run_cli("install", "--quiet", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all outdated packages.

        ``brew`` and ``cask`` share the same command, but ``cask`` overrides this
        method to append ``--greedy`` when auto-updating packages are included.

        .. code-block:: shell-session

            $ brew upgrade --formula
            ==> Upgrading 2 outdated packages:
            node 13.11.0 -> 13.12.0
            sdl2 2.0.12 -> 2.0.12_1
            ==> Upgrading node 13.11.0 -> 13.12.0
            ==> Downloading https://homebrew.bintray.com/bottles/node-13.tar.gz
            ==> Downloading from https://akamai.bintray.com/fc/fc0bfb42fe23e960
            ############################################################ 100.0%
            ==> Pouring node-13.12.0.catalina.bottle.tar.gz
            ==> Caveats
            Bash completion has been installed to:
              /usr/local/etc/bash_completion.d
            ==> Summary
            🍺  /usr/local/Cellar/node/13.12.0: 4,660 files, 60.3MB
            Removing: /usr/local/Cellar/node/13.11.0... (4,686 files, 60.4MB)
            ==> Upgrading sdl2 2.0.12 -> 2.0.12_1
            ==> Downloading https://homebrew.bintray.com/bottles/sdl2-2.tar.gz
            ==> Downloading from https://akamai.bintray.com/4d/4dcd635465d16372
            ############################################################ 100.0%
            ==> Pouring sdl2-2.0.12_1.catalina.bottle.tar.gz
            🍺  /usr/local/Cellar/sdl2/2.0.12_1: 89 files, 4.7MB
            Removing: /usr/local/Cellar/sdl2/2.0.12... (89 files, 4.7MB)
            ==> Checking for dependents of upgraded formulae...
            ==> No dependents found!
            ==> Caveats
            ==> node
            Bash completion has been installed to:
              /usr/local/etc/bash_completion.d

        .. code-block:: shell-session

            $ brew upgrade --cask
            ==> Casks with `auto_updates` or `version :latest` will not be upgraded
            ==> Upgrading 1 outdated packages:
            aerial 2.0.7 -> 2.0.8
            ==> Upgrading aerial
            ==> Downloading https://github.com/Aerial/download/v2.0.8/Aerial.saver.zip
            ==> Downloading from https://65be.s3.amazonaws.com/44998092/29eb1e0
            ==> Verifying SHA-256 checksum for Cask 'aerial'.
            ==> Backing Screen Saver up to '/usr/local/Caskroom/Aerial.saver'.
            ==> Removing Screen Saver '/Users/kde/Library/Screen Savers/Aerial.saver'.
            ==> Moving Screen Saver to '/Users/kde/Library/Screen Savers/Aerial.saver'.
            ==> Purging files for version 2.0.7 of Cask aerial
            🍺  aerial was successfully upgraded!

        ``--yes`` skips the interactive confirmation prompt that ``brew`` shows by
        default since ask mode became the default behaviour.
        """
        return self.build_cli("upgrade", "--quiet", "--yes")

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the provided package.

        ``brew`` and ``cask`` share the same command.

        .. code-block:: shell-session

            $ brew upgrade dupeguru --cask
            ==> Upgrading 1 outdated package:
            dupeguru 4.2.0 -> 4.2.1
            ==> Upgrading dupeguru
            ==> Downloading https://github.com/(...)/4.2.1/dupeguru_macOS_Qt_4.2.1.zip
            ==> Downloading from https://githubusercontent.com/production-release-asset
            ##################################################################### 100.0%
            ==> Backing App 'dupeguru.app' up to '/opt/homebrew/.../4.2.0/dupeguru.app'
            ==> Removing App '/Applications/dupeguru.app'
            ==> Moving App 'dupeguru.app' to '/Applications/dupeguru.app'
            ==> Purging files for version 4.2.0 of Cask dupeguru
            🍺  dupeguru was successfully upgraded!

        ``--yes`` skips the interactive confirmation prompt that ``brew`` shows by
        default since ask mode became the default behaviour.
        """
        return self.build_cli("upgrade", "--quiet", "--yes", package_id)

    def remove(self, package_id: str) -> str:
        """Removes a package.

        .. code-block:: shell-session

            $ brew uninstall bat
            Uninstalling /usr/local/Cellar/bat/0.21.0... (14 files, 5MB)
        """
        return self.run_cli("uninstall", "--quiet", package_id)

    def sync(self) -> None:
        """Sync package metadata.

        .. code-block:: shell-session

            $ brew update --quiet
            Already up-to-date.
        """
        self.run_cli("update", "--quiet", auto_post_args=False)

    def cleanup(self) -> None:
        """Removes things we don't need anymore.

        First remove unused dependencies (see :py:meth:`cleanup_orphan`), then scrub
        the cache, including latest version's downloads. Downloads for all installed
        formulae and casks will not be deleted.

        .. code-block:: shell-session

            $ brew cleanup -s --prune=all
            Removing: ~/Library/Caches/Homebrew/node--1.bottle.tar.gz... (9MB)
            Warning: Skipping sdl2: most recent version 2.0.12_1 not installed
            Removing: ~/Library/Caches/Homebrew/Cask/aerial--1.8.1.zip... (5MB)
            Removing: ~/Library/Caches/Homebrew/Cask/prey--1.9.pkg... (19.9MB)
            Removing: ~/Library/Logs/Homebrew/readline... (64B)
            Removing: ~/Library/Logs/Homebrew/libfido2... (64B)
            Removing: ~/Library/Logs/Homebrew/libcbor... (64B)

        More doc at: https://docs.brew.sh/Manpage#cleanup
        """
        self.cleanup_orphan()
        self.run_cli("cleanup", "--quiet", "-s", "--prune=all", auto_post_args=False)

    def cleanup_orphan(self) -> None:
        """Uninstall every formula installed as a dependency and no longer needed.

        .. code-block:: shell-session

            $ brew autoremove
            ==> Uninstalling 17 unneeded formulae:
            gtkmm3
            highlight
            lua@5.1
            nasm
            nghttp2
            texi2html
            Uninstalling /usr/local/Cellar/nghttp2/1.41.0_1... (26 files, 2.7MB)
            Uninstalling /usr/local/Cellar/highlight/3.59... (558 files, 3.5MB)

            Warning: The following highlight configuration files have not been removed!
            If desired, remove them manually with `rm -rf`:
              /usr/local/etc/highlight
              /usr/local/etc/highlight/filetypes.conf
              /usr/local/etc/highlight/filetypes.conf.default
            Uninstalling /usr/local/Cellar/gtkmm3/3.24.2_1... (1,903 files, 173.7MB)
            Uninstalling /usr/local/Cellar/texi2html/5.0... (279 files, 6.2MB)
            Uninstalling /usr/local/Cellar/lua@5.1/5.1.5_8... (22 files, 245.6KB)
            Uninstalling /usr/local/Cellar/nasm/2.15.05... (29 files, 2.9MB)
        """
        self.run_cli("autoremove", "--quiet", auto_post_args=False)


class Brew(Homebrew):
    """The formula half of Homebrew: command-line tools built from recipes.

    Homebrew is the umbrella project behind the ``brew`` CLI. mpm splits it into
    two managers over the same binary, this one for formulae and :py:class:`Cask`
    for macOS applications; a forced ``--formula`` selector keeps every call on
    the formula side. Homebrew core runs on macOS and on `Linux and WSL
    <https://docs.brew.sh/Homebrew-on-Linux>`_.

    mpm drives ``brew`` non-interactively and pins its environment: analytics and
    setup hints are silenced, and ``HOMEBREW_NO_AUTO_UPDATE`` keeps ``brew`` from
    folding a metadata refresh into every command, since mpm runs that as a
    separate ``sync`` (`asked for since mpm's early days
    <https://github.com/kdeldycke/meta-package-manager/issues/36>`_). Outdated
    packages come from ``--json=v2``; the installed and search listings are
    parsed from their plain-text columns.

    .. note::

        The ``>=6.0.0`` requirement is the release where ask mode became the
        default for ``brew install`` and ``brew upgrade``, and where the
        ``--yes`` opt-out mpm relies on for unattended runs first shipped. It is
        also where Homebrew began rejecting third-party taps until trusted, so
        installing a fully-qualified ``user/tap/name`` package taps and trusts it
        first (see :py:meth:`Homebrew.trust_tap`).

    .. caution::

        A pinned formula still appears in ``mpm outdated`` output, yet
        ``brew upgrade`` silently skips it: mpm discards Homebrew's ``pinned``
        fields today.
    """

    name = "Homebrew Formulae"

    homepage_url = "https://brew.sh"

    brewfile_entry_type = "brew"

    cli_names = ("brew",)

    post_args = ("--formula",)


class Cask(Homebrew):
    """The cask half of Homebrew: pre-built macOS applications.

    Homebrew is the umbrella project behind the ``brew`` CLI. mpm splits it into
    two managers over the same binary, this one for casks and :py:class:`Brew`
    for formulae; a forced ``--cask`` selector keeps every call on the cask side.
    Casks ship macOS ``.app`` bundles and ``.pkg`` installers, so this manager is
    macOS-only.

    mpm drives ``brew`` non-interactively with the same environment pins as
    :py:class:`Brew` (analytics and hints off, ``HOMEBREW_NO_AUTO_UPDATE`` so the
    metadata refresh stays a separate ``sync``) and the same ``>=6.0.0`` floor
    (ask mode default, the ``--yes`` opt-out, and the tap-trust gate that
    :py:meth:`Homebrew.trust_tap` clears for ``user/tap/name`` packages).

    .. note::

        Casks self-escalate: their artifacts (``.pkg`` installers, kernel
        extensions) invoke ``sudo`` from inside ``brew``, so mpm never wraps a
        cask command in its own ``sudo``.

    .. caution::

        Casks flagged ``auto_updates true`` or ``version :latest`` update
        themselves, and ``brew upgrade`` skips them unless ``--greedy`` is
        passed. mpm supplies ``--greedy`` (to ``outdated`` and to
        ``upgrade --all``) unless auto-updating packages are being ignored.
        ``--greedy`` conflicts with ``--formula``, so this handling is cask-only
        and cannot fold into the base shared with :py:class:`Brew`.
    """

    name = "Homebrew Cask"

    homepage_url = "https://github.com/Homebrew/homebrew-cask"

    brewfile_entry_type = "cask"

    platforms = MACOS  # type: ignore[assignment]
    """Casks are only available on macOS, not Linux or WSL."""

    internal_sudo = True
    """Cask artifacts (``.pkg`` installers, kernel extensions) run ``sudo`` from
    inside ``brew``."""

    cli_names = ("brew",)

    post_args = ("--cask",)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all outdated packages.

        Adds ``--greedy`` to the shared ``brew upgrade`` command when auto-updating
        packages are included, mirroring :py:meth:`Homebrew.outdated`. Without it,
        ``brew upgrade`` skips casks flagged ``auto_updates true`` or
        ``version :latest``, so ``mpm --include-auto-updates upgrade --all`` would
        report them as outdated but never upgrade them.

        .. note::

            This override is cask-only by necessity: ``brew upgrade`` declares
            ``--greedy`` and ``--formula`` mutually exclusive, while
            ``brew outdated`` accepts the pair. The conflict is intentional:
            ``--formula`` has conflicted with ``--greedy`` ever since the selector
            switch `was added to brew upgrade in August 2020
            <https://github.com/Homebrew/brew/pull/8229>`_, and a request to
            tolerate ``--greedy`` as a no-op in formula-only contexts `was
            declined as invalid usage
            <https://github.com/Homebrew/brew/issues/16135>`_. This method can
            therefore never fold back into the base class shared with ``brew``.

            A cask explicitly passed to ``brew upgrade`` is always evaluated
            greedily, so :py:meth:`Homebrew.upgrade_one_cli` needs no counterpart.
        """
        options = ["--quiet", "--yes"]
        # Includes auto-update packages or not.
        if not self.ignore_auto_updates:
            options.append("--greedy")
        return self.build_cli("upgrade", options)
