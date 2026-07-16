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

import atexit
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from functools import cached_property
from importlib import resources
from pathlib import Path

from extra_platforms import UNIX_WITHOUT_MACOS

from ..capabilities import search_capabilities, version_not_implemented
from ..manager import PackageManager
from ..version import VersionRange

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from click_extra.envvar import TEnvVars

    from ..package import Package


_YAY_COOLDOWN_INIT_LUA = (
    resources
    .files("meta_package_manager.managers")
    .joinpath("yay_cooldown.lua")
    .read_text(encoding="UTF-8")
)
"""Lua policy mpm drops into the overlay's ``init.lua`` to express the release-age
:py:attr:`cooldown <meta_package_manager.execution.CLIExecutor.cooldown>` for yay.

The policy itself lives in the sibling ``yay_cooldown.lua`` file and is read here
through :py:mod:`importlib.resources` so it stays editable and syntax-highlightable as
real Lua. Static on purpose: the only per-run input is the ``MPM_COOLDOWN_EPOCH``
environment variable, so the file never has to be regenerated. It registers two hooks
(both keyed off the same cutoff) and first chains the user's real ``init.lua`` so
nothing in their config is lost. See :py:meth:`Yay.cooldown_env` for how it is
delivered.
"""


class Pacman(PackageManager):
    """See command equivalences at: https://wiki.archlinux.org/title/Pacman/Rosetta."""

    name = "Arch Linux pacman"

    homepage_url = "https://wiki.archlinux.org/title/pacman"

    platforms = UNIX_WITHOUT_MACOS

    default_sudo = True

    requirement = ">=5.0.0"

    pre_args = ("--noconfirm", "--color", "never")

    _INSTALLED_REGEXP = re.compile(r"(\S+) (\S+)")
    _OUTDATED_REGEXP = re.compile(r"(\S+) (\S+) -> (\S+)")
    _SEARCH_REGEXP = re.compile(
        r"(?P<repo_id>\S+?)/(?P<package_id>\S+)\s+(?P<version>\S+).*\n\s+(?P<description>.+)",
        re.MULTILINE | re.VERBOSE,
    )

    version_regexes = (r".*Pacman\s+v(?P<version>\S+)",)
    r"""Search version right after the ``Pacman `` string.

    .. code-block:: shell-session

        $ pacman --version

         .--.                  Pacman v6.0.1 - libalpm v13.0.1
        / _.-' .-.  .-.  .-.   Copyright (C) 2006-2021 Pacman Development Team
        \  '-. '-'  '-'  '-'   Copyright (C) 2002-2006 Judd Vinet
         '--'
                            This program may be freely redistributed under
                            the terms of the GNU General Public License.
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            $ pacman --noconfirm --query
            a52dec 0.7.4-11
            aalib 1.4rc5-14
            abseil-cpp 20211102.0-2
            accountsservice 22.08.8-2
            acl 2.3.1-2
            acme.sh 3.0.2-1
            acpi 1.7-3
            acpid 2.0.33-1
        """
        output = self.run_cli("--query")

        for package in output.splitlines():
            match = self._INSTALLED_REGEXP.match(package)
            if match:
                package_id, installed_version = match.groups()
                yield self.package(id=package_id, installed_version=installed_version)

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            $ pacman --noconfirm --query --upgrades
            linux 4.19.1.arch1-1 -> 4.19.2.arch1-1
            linux-headers 4.19.1.arch1-1 -> 4.19.2.arch1-1

        .. note::
            ``pacman --query --upgrades`` (``-Qu``) only reports updates for
            packages tracked in a sync database (official repos, plus any
            local repo configured in ``pacman.conf``). Foreign packages, those
            installed with ``pacman -U`` as most AUR helpers do, are invisible
            to ``-Qu`` and surface only under ``-Qm``.

            The ``Pacaur``, ``Paru`` and ``Yay`` subclasses inherit this method
            verbatim, yet still see AUR updates because their own binary's
            ``-Qu`` additionally queries the AUR RPC for foreign packages. The
            per-subclass binary override is therefore load-bearing: routing
            these helpers through ``pacman`` directly would silently drop every
            AUR update from the results.

            .. caution::
                This follows upstream ``-Qu`` semantics but has not been
                confirmed on a live Arch box. Before relying on it, verify that
                ``yay --query --upgrades`` invoked through mpm actually surfaces
                a pending AUR update.
        """
        output = self.run_cli("--query", "--upgrades")

        for package in output.splitlines():
            match = self._OUTDATED_REGEXP.match(package)
            if match:
                package_id, installed_version, latest_version = match.groups()
                yield self.package(
                    id=package_id,
                    latest_version=latest_version,
                    installed_version=installed_version,
                )

    @search_capabilities(extended_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. caution::
            Search does not supports extended matching.

        .. code-block:: shell-session

            $ pacman --noconfirm --sync --search fire
            extra/dump_syms 0.0.7-1
                Symbol dumper for Firefox
            extra/firefox 99.0-1
                Standalone web browser from mozilla.org
            extra/firefox-i18n-ach 99.0-1
                Acholi language pack for Firefox
            extra/firefox-i18n-af 99.0-1
                Afrikaans language pack for Firefox
            extra/firefox-i18n-an 99.0-1
                Aragonese language pack for Firefox
            extra/firefox-i18n-ar 99.0-1
                Arabic language pack for Firefox
            extra/firefox-i18n-ast 99.0-1
                Asturian language pack for Firefox
        """
        if exact:
            query = f"^{query}$"

        output = self.run_cli("--sync", "--search", query)

        for _repo_id, package_id, version, description in self._SEARCH_REGEXP.findall(
            output,
        ):
            yield self.package(
                id=package_id,
                description=description,
                latest_version=version,
            )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            $ sudo pacman --noconfirm --color never --sync firefox
        """
        return self.run_cli("--sync", package_id, sudo=True)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade the package provided as parameter.

        .. code-block:: shell-session

            $ sudo pacman --noconfirm --color never --sync --refresh --sysupgrade
        """
        return self.build_cli("--sync", "--refresh", "--sysupgrade", sudo=True)

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the package provided as parameter.

        .. code-block:: shell-session

            $ sudo pacman --noconfirm --color never --sync firefox
        """
        return self.build_cli("--sync", package_id, sudo=True)

    def remove(self, package_id: str) -> str:
        """Removes a package.

        .. code-block:: shell-session

            $ sudo pacman --noconfirm --color never --remove firefox
        """
        return self.run_cli("--remove", package_id, sudo=True)

    def sync(self) -> None:
        """Sync package metadata.

        .. code-block:: shell-session

            $ pacman --noconfirm --color never --sync --refresh
        """
        self.run_cli("--sync", "--refresh")

    def cleanup(self) -> None:
        """Removes things we don't need anymore.

        .. code-block:: shell-session

            $ sudo pacman --noconfirm --color never --sync --clean --clean
        """
        self.run_cli("--sync", "--clean", "--clean", sudo=True)


class Pacaur(Pacman):
    """``Pacaur`` wraps ``pacman`` and shadows its options."""

    name = "Arch Linux pacaur"

    homepage_url = "https://github.com/E5ten/pacaur"

    requirement = ">=4.0.0"

    version_regexes = (r"pacaur\s+(?P<version>\S+)",)
    r"""Search version right after the ``pacaur`` string.

    .. code-block:: shell-session

        $ pacaur --version
        pacaur 4.8.6
    """


class Paru(Pacman):
    """``paru`` wraps ``pacman`` and shadows its options."""

    name = "Arch Linux paru"

    homepage_url = "https://github.com/Morganamilo/paru"

    # v1.9.3 is the first version implementing the --sysupgrade option.
    requirement = ">=1.9.3"

    version_regexes = (r"paru\s+v(?P<version>\S+)",)
    r"""Search version right after the ``paru`` string.

    .. code-block:: shell-session

        $ paru --version
        paru v1.10.0 - libalpm v13.0.1
    """


class Yay(Pacman):
    """``yay`` wraps ``pacman`` and shadows its options.

    .. note::
        yay exposes no release-age flag, so mpm enforces the supply-chain
        :py:attr:`cooldown <meta_package_manager.execution.CLIExecutor.cooldown>` by
        overlaying a generated ``init.lua`` through a private ``XDG_CONFIG_HOME`` (see
        :py:meth:`cooldown_env`). This needs yay >= 13.0.0, when the Lua
        ``UpgradeSelect``/``AURPreInstall`` hooks landed; an older yay stays a usable
        manager but cannot honor a cooldown. The upstream request for a less invasive
        injection point is https://github.com/Jguer/yay/issues/2883.
    """

    name = "Arch Linux yay"

    homepage_url = "https://github.com/Jguer/yay"

    requirement = ">=11.0.0"

    cooldown_env_var = "XDG_CONFIG_HOME"
    """yay reads no release-age option of its own, so mpm repurposes ``XDG_CONFIG_HOME``
    to point yay at the throwaway config overlay built by :py:meth:`cooldown_env`.

    Unlike the single-value variables of pip/uv/npm, the value is a *directory*; the
    cutoff itself rides alongside it in ``MPM_COOLDOWN_EPOCH``. Set so the structural
    ``supports_cooldown`` check (and the ``--cooldown`` help text) still recognize yay
    as cooldown-capable.
    """

    version_regexes = (r"yay\s+v(?P<version>\S+)",)
    r"""Search version right after the ``yay`` string.

    .. code-block:: shell-session

        $ yay --version
        yay v11.1.2 - libalpm v13.0.1
    """

    cooldown_requirement = ">=13.0.0"
    """Minimum yay version whose Lua hooks the cooldown overlay relies on.

    `v13.0.0 <https://github.com/Jguer/yay/releases/tag/v13.0.0>`_ introduced
    ``yay.create_autocmd`` and the ``UpgradeSelect``/``AURPreInstall`` events. Kept
    apart from :py:attr:`requirement` (``>=11.0.0``) so a v11/v12 yay stays fully
    usable for everything except the cooldown.
    """

    _resolving_cooldown_env = False
    """Re-entrancy guard for :py:meth:`cooldown_env`.

    Held while :py:meth:`cooldown_env` resolves :py:attr:`supports_cooldown`, whose
    :py:attr:`version <meta_package_manager.execution.CLIExecutor.version>` lookup runs
    ``yay --version`` through :py:meth:`run`, which calls straight back into
    :py:meth:`cooldown_env`. The nested call returns early so the probe runs without a
    cooldown env instead of recursing until the stack overflows.
    """

    @property
    def supports_cooldown(self) -> bool:
        """Whether this yay can natively enforce a release-age cooldown.

        Reports the structural capability while idle (``cooldown is None``) so the
        import-time ``COOLDOWN_SUPPORTED_MANAGERS`` help text stays I/O-free, and only
        probes the manager
        :py:attr:`version <meta_package_manager.execution.CLIExecutor.version>` once a
        cooldown is active, gating on :py:attr:`cooldown_requirement`. A yay older than
        that (or undetectable) reports no support, so the fail-closed default skips
        install/upgrade rather than running them unguarded.
        """
        if self.cooldown is None:
            return self.cooldown_env_var is not None
        if self.version is None:
            return False
        return self.version in VersionRange(self.cooldown_requirement)

    def cooldown_env(self) -> TEnvVars:
        """Deliver the release-age cooldown through a private ``XDG_CONFIG_HOME``.

        yay has no release-age option, so rather than injecting a single value mpm
        points yay at :py:attr:`_cooldown_overlay_dir`: a throwaway config tree whose
        generated ``init.lua`` (:py:data:`_YAY_COOLDOWN_INIT_LUA`) registers the
        cooldown Lua hooks. The cutoff travels as ``MPM_COOLDOWN_EPOCH`` (Unix seconds
        of ``now - cooldown``), keeping the ``init.lua`` asset static, and
        ``MPM_YAY_USER_DIR`` lets it chain the user's real config so the redirect stays
        lossless.

        Returns an empty mapping when no cooldown is set or the installed yay predates
        the Lua hooks (see :py:attr:`supports_cooldown`).
        """
        if self.cooldown is None:
            return {}
        # Resolving `supports_cooldown` reads `version`, which runs `yay --version`
        # through `run()`, re-entering this method. Break that loop: a version probe
        # needs no cooldown env, and the outer call finishes once `version` is cached.
        if self._resolving_cooldown_env:
            return {}
        self._resolving_cooldown_env = True
        try:
            if not self.supports_cooldown:
                return {}
            cutoff = datetime.now(tz=timezone.utc) - self.cooldown
            # Clamp to the Unix epoch: a cooldown reaching before 1970 yields a
            # negative timestamp, and yay's Lua (gopher-lua) parses that back to nil,
            # which silently drops the gate. Epoch 0 keeps the floor effective (every
            # real release post-dates 1970, so all are held back, as an overlong
            # cooldown intends).
            epoch = max(0, int(cutoff.timestamp()))
            env = {
                "XDG_CONFIG_HOME": str(self._cooldown_overlay_dir),
                "MPM_COOLDOWN_EPOCH": str(epoch),
            }
            user_dir = self._user_yay_config_dir()
            if user_dir is not None:
                env["MPM_YAY_USER_DIR"] = str(user_dir)
            return env
        finally:
            self._resolving_cooldown_env = False

    @staticmethod
    def _user_yay_config_dir() -> Path | None:
        """Resolve the user's real yay config directory using yay's own precedence.

        Mirrors ``GetConfigPath``/``GetLuaConfigPath`` in yay's
        ``pkg/settings/dirs.go``: ``$XDG_CONFIG_HOME/yay`` wins over
        ``$HOME/.config/yay``. Returns ``None`` when neither variable is set, matching
        yay falling back to its built-in defaults.

        .. caution::
            Read from :py:data:`os.environ` *before* mpm overrides ``XDG_CONFIG_HOME``
            for the child, so it resolves the user's genuine directory, not the overlay.
        """
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config:
            return Path(xdg_config) / "yay"
        home = os.environ.get("HOME")
        if home:
            return Path(home) / ".config" / "yay"
        return None

    @cached_property
    def _cooldown_overlay_dir(self) -> Path:
        """Materialize the private config tree mpm points yay at for the cooldown.

        Built once per manager instance and removed at interpreter exit. The tree holds
        two entries under ``<root>/yay/``:

        - ``init.lua``: the static :py:data:`_YAY_COOLDOWN_INIT_LUA` policy.
        - ``config.json``: a symlink to the user's real config, so the
          ``XDG_CONFIG_HOME`` redirect stays lossless. yay's ``init.lua`` only
          *overlays* ``config.json``; it does not replace it, so the user's settings are
          preserved.

        Only those two paths are placed here because they are the sole files yay derives
        from ``XDG_CONFIG_HOME`` (per ``dirs.go``); its cache, build dir and
        ``vcs.json`` follow ``XDG_CACHE_HOME``/``HOME`` and are untouched by the
        redirect.

        .. warning::
            Cleanup is registered with :py:func:`atexit`, **not**
            ``weakref.finalize(self, ...)``. The overlay must outlive every yay
            subprocess that reads it, and yay re-reads ``init.lua`` mid-run (it re-execs
            during an install that pulls dependencies). Tying removal to this instance's
            garbage collection raced that re-read: if the manager was collected after
            :py:meth:`cooldown_env` but before yay finished, the overlay vanished and
            the gate silently failed *open*: the worst outcome for a supply-chain
            control. Process-lifetime cleanup is a safe upper bound; the tree is tiny.
        """
        root = Path(tempfile.mkdtemp(prefix="mpm-yay-cooldown-"))
        atexit.register(shutil.rmtree, root, ignore_errors=True)

        config_dir = root / "yay"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "init.lua").write_text(_YAY_COOLDOWN_INIT_LUA, encoding="UTF-8")

        user_dir = self._user_yay_config_dir()
        if user_dir is not None:
            user_config = user_dir / "config.json"
            if user_config.is_file():
                (config_dir / "config.json").symlink_to(user_config)
        return root
